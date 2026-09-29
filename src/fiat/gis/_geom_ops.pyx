# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
"""From-scratch 2D geometry predicates for FIAT (no GEOS / GDAL).

Operates directly on the flat coordinate representation produced by the
FlatGeobuf driver (:class:`fiat.driver._fgb.fgb.Geometry`):

* ``xy``    - flat interleaved x, y coordinates (float64),
* ``ends``  - cumulative coordinate-pair counts per ring/line (uint32),
* ``parts`` - cumulative ring counts per polygon for MultiPolygon (uint32).

The predicates reproduce the subset of OGR/GEOS behaviour FIAT relies on:
point-in-polygon, polygon/cell intersection, and a representative interior
point (a replacement for ``OGRGeometry::PointOnSurface``).
"""

import numpy as np

cimport numpy as cnp

cnp.import_array()


# --- Low level helpers ----------------------------------------------------
cdef inline bint _point_in_rings(const double* xy, const unsigned int* ends,
                                 int ring_start, int ring_end,
                                 double x, double y) noexcept nogil:
    """Even-odd point-in-polygon test across rings [ring_start, ring_end)."""
    cdef bint inside = False
    cdef int r, i, j, seg_start, seg_end
    cdef double xi, yi, xj, yj
    for r in range(ring_start, ring_end):
        seg_start = ends[r - 1] if r > 0 else 0
        seg_end = ends[r]
        j = seg_end - 1
        for i in range(seg_start, seg_end):
            xi = xy[2 * i]
            yi = xy[2 * i + 1]
            xj = xy[2 * j]
            yj = xy[2 * j + 1]
            if ((yi > y) != (yj > y)) and \
               (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
    return inside


cdef bint _point_in_geom(const double* xy, const unsigned int* ends,
                         int n_ends, const unsigned int* parts, int n_parts,
                         double x, double y) noexcept nogil:
    """Point-in-geometry across a (multi)polygon."""
    cdef int p, ring_start, ring_end
    if n_ends == 0:
        return False
    if n_parts == 0:
        return _point_in_rings(xy, ends, 0, n_ends, x, y)
    for p in range(n_parts):
        ring_start = parts[p - 1] if p > 0 else 0
        ring_end = parts[p]
        if _point_in_rings(xy, ends, ring_start, ring_end, x, y):
            return True
    return False


cdef inline bint _on_seg(double ax, double ay, double bx, double by,
                         double px, double py) noexcept nogil:
    """Return True if point P lies on segment AB (assuming collinear)."""
    return (min(ax, bx) <= px <= max(ax, bx)) and \
           (min(ay, by) <= py <= max(ay, by))


cdef inline bint _seg_seg(double ax, double ay, double bx, double by,
                          double cx, double cy, double dx, double dy) noexcept nogil:
    """Return True if segment AB intersects segment CD."""
    cdef double d1 = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
    cdef double d2 = (bx - ax) * (dy - ay) - (by - ay) * (dx - ax)
    cdef double d3 = (dx - cx) * (ay - cy) - (dy - cy) * (ax - cx)
    cdef double d4 = (dx - cx) * (by - cy) - (dy - cy) * (bx - cx)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return True
    # Collinear/touching cases treated as intersecting when overlapping.
    if d1 == 0 and _on_seg(ax, ay, bx, by, cx, cy):
        return True
    if d2 == 0 and _on_seg(ax, ay, bx, by, dx, dy):
        return True
    if d3 == 0 and _on_seg(cx, cy, dx, dy, ax, ay):
        return True
    if d4 == 0 and _on_seg(cx, cy, dx, dy, bx, by):
        return True
    return False


cdef inline bint _edge_hits_cell(double px, double py, double qx, double qy,
                                 double minx, double miny, double maxx,
                                 double maxy) noexcept nogil:
    """Return True if segment PQ intersects the cell boundary."""
    return (_seg_seg(px, py, qx, qy, minx, miny, maxx, miny) or
            _seg_seg(px, py, qx, qy, maxx, miny, maxx, maxy) or
            _seg_seg(px, py, qx, qy, maxx, maxy, minx, maxy) or
            _seg_seg(px, py, qx, qy, minx, maxy, minx, miny))


cdef bint _intersect_cell(const double* xy, int n_xy, const unsigned int* ends,
                          int n_ends, const unsigned int* parts, int n_parts,
                          int geom_type, double minx, double miny, double maxx,
                          double maxy) noexcept nogil:
    """Return True if a geometry intersects an axis-aligned cell."""
    cdef int total_pairs, i, r, seg_start, seg_end, last
    cdef double px, py, qx, qy
    cdef double cx = 0.5 * (minx + maxx)
    cdef double cy = 0.5 * (miny + maxy)

    total_pairs = n_xy // 2
    if total_pairs == 0:
        return False

    # 1. Any geometry vertex inside the cell (covers points and partial overlap).
    for i in range(total_pairs):
        px = xy[2 * i]
        py = xy[2 * i + 1]
        if minx <= px <= maxx and miny <= py <= maxy:
            return True

    # Points: only the vertex test applies.
    if geom_type == 1 or geom_type == 4:
        return False

    # Polygons: cell centre inside the polygon (cell fully covered).
    if geom_type == 3 or geom_type == 6:
        if _point_in_geom(xy, ends, n_ends, parts, n_parts, cx, cy):
            return True

    # 2/3. Edges crossing a cell edge. Polygons close each ring; lines do not.
    cdef bint close = (geom_type == 3 or geom_type == 6)
    if n_ends == 0:
        # Single open sequence over all vertices.
        for i in range(total_pairs - 1):
            px = xy[2 * i]
            py = xy[2 * i + 1]
            qx = xy[2 * i + 2]
            qy = xy[2 * i + 3]
            if _edge_hits_cell(px, py, qx, qy, minx, miny, maxx, maxy):
                return True
        return False

    for r in range(n_ends):
        seg_start = ends[r - 1] if r > 0 else 0
        seg_end = ends[r]
        if seg_end - seg_start < 2:
            continue
        for i in range(seg_start, seg_end - 1):
            px = xy[2 * i]
            py = xy[2 * i + 1]
            qx = xy[2 * i + 2]
            qy = xy[2 * i + 3]
            if _edge_hits_cell(px, py, qx, qy, minx, miny, maxx, maxy):
                return True
        if close:
            last = seg_end - 1
            px = xy[2 * last]
            py = xy[2 * last + 1]
            qx = xy[2 * seg_start]
            qy = xy[2 * seg_start + 1]
            if _edge_hits_cell(px, py, qx, qy, minx, miny, maxx, maxy):
                return True
    return False


# --- Array extraction -----------------------------------------------------
cdef inline object _as_xy(object geom):
    return np.ascontiguousarray(geom.xy, dtype=np.float64)


cdef inline object _as_ends(object geom):
    return np.ascontiguousarray(geom.ends, dtype=np.uint32)


cdef inline object _as_parts(object geom):
    return np.ascontiguousarray(geom.parts, dtype=np.uint32)


# --- Public API -----------------------------------------------------------
def point_in_geometry(object geom, double x, double y):
    """Return whether point ``(x, y)`` lies inside a (multi)polygon geometry."""
    cdef double[::1] xy = _as_xy(geom)
    cdef unsigned int[::1] ends = _as_ends(geom)
    cdef unsigned int[::1] parts = _as_parts(geom)
    cdef int n_ends = ends.shape[0]
    cdef int n_parts = parts.shape[0]
    if n_ends == 0:
        return False
    return bool(_point_in_geom(&xy[0], &ends[0], n_ends,
                               &parts[0] if n_parts else <unsigned int*>0,
                               n_parts, x, y))


def intersect_cell(object geom, double x, double y, double dx, double dy):
    """Return whether ``geom`` intersects the cell at ``(x, y)`` of size ``dx, dy``."""
    cdef double minx = min(x, x + dx)
    cdef double maxx = max(x, x + dx)
    cdef double miny = min(y, y + dy)
    cdef double maxy = max(y, y + dy)
    # Quick envelope reject.
    if geom.maxx < minx or geom.minx > maxx or \
       geom.maxy < miny or geom.miny > maxy:
        return False
    cdef double[::1] xy = _as_xy(geom)
    cdef unsigned int[::1] ends = _as_ends(geom)
    cdef unsigned int[::1] parts = _as_parts(geom)
    cdef int n_xy = xy.shape[0]
    cdef int n_ends = ends.shape[0]
    cdef int n_parts = parts.shape[0]
    cdef int geom_type = geom.type
    if n_xy == 0:
        return False
    return bool(_intersect_cell(&xy[0], n_xy,
                                &ends[0] if n_ends else <unsigned int*>0, n_ends,
                                &parts[0] if n_parts else <unsigned int*>0,
                                n_parts, geom_type, minx, miny, maxx, maxy))


def point_on_surface(object geom):
    """Return a representative interior point ``(x, y)`` of a polygon geometry.

    Mirrors ``OGRGeometry::PointOnSurface``: tries the exterior-ring centroid and,
    if that falls outside (e.g. concave shapes or holes), falls back to the
    midpoint of the widest interior span of a horizontal scanline.
    """
    cdef double[::1] xy = _as_xy(geom)
    cdef unsigned int[::1] ends = _as_ends(geom)
    cdef unsigned int[::1] parts = _as_parts(geom)
    cdef int n_ends = ends.shape[0]
    cdef int n_parts = parts.shape[0]
    cdef int gtype = geom.type
    cdef int i, r, seg_start, seg_end, j, n0
    cdef double area = 0.0, cxs = 0.0, cys = 0.0, cross
    cdef double xi, yi, xj, yj
    cdef int npts = xy.shape[0] // 2

    if npts == 0:
        return (0.0, 0.0)

    # Point geometries: return the first coordinate.
    if gtype == 1 or gtype == 4:
        return (xy[0], xy[1])

    # Line geometries: return the middle vertex.
    if gtype == 2 or gtype == 5:
        return (xy[2 * (npts // 2)], xy[2 * (npts // 2) + 1])

    if n_ends == 0 or xy.shape[0] < 2:
        return (xy[0], xy[1])

    # Shoelace centroid of the exterior ring (ring 0).
    n0 = ends[0]
    j = n0 - 1
    for i in range(0, n0):
        xi = xy[2 * i]
        yi = xy[2 * i + 1]
        xj = xy[2 * j]
        yj = xy[2 * j + 1]
        cross = xj * yi - xi * yj
        area += cross
        cxs += (xj + xi) * cross
        cys += (yj + yi) * cross
        j = i

    cdef double cx, cy
    if area != 0.0:
        cx = cxs / (3.0 * area)
        cy = cys / (3.0 * area)
    else:
        cx = xy[0]
        cy = xy[1]

    if _point_in_geom(&xy[0], &ends[0], n_ends,
                      &parts[0] if n_parts else <unsigned int*>0,
                      n_parts, cx, cy):
        return (cx, cy)

    # Scanline fallback at y = cy: collect x-crossings across every ring.
    cdef list xs = []
    for r in range(n_ends):
        seg_start = ends[r - 1] if r > 0 else 0
        seg_end = ends[r]
        j = seg_end - 1
        for i in range(seg_start, seg_end):
            xi = xy[2 * i]
            yi = xy[2 * i + 1]
            xj = xy[2 * j]
            yj = xy[2 * j + 1]
            if (yi > cy) != (yj > cy):
                xs.append((xj - xi) * (cy - yi) / (yj - yi) + xi)
            j = i
    if not xs:
        return (cx, cy)
    xs.sort()
    cdef double best = -1.0, bx = cx
    cdef Py_ssize_t k
    for k in range(0, len(xs) - 1, 2):
        if xs[k + 1] - xs[k] > best:
            best = xs[k + 1] - xs[k]
            bx = 0.5 * (xs[k] + xs[k + 1])
    return (bx, cy)
