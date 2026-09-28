# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
"""Fast rasterisation of a geometry footprint onto a grid window.

``cell_mask`` reproduces the per-cell ``geom.Intersects(cell)`` loop that used
to build one ``ogr.Geometry`` per cell. The geometry is flattened once (rings
for polygons, vertices for lines) and every cell of the window is tested in C:

* a cell intersects the geometry when any geometry segment overlaps the cell
  rectangle (Liang-Barsky clip, boundary inclusive), or
* for areal geometries, when the cell centre falls inside the polygon
  (even-odd ray casting over all rings, holes included).

This matches OGR/GEOS ``Intersects`` semantics for the polygon and line inputs
used by FIAT while removing the SWIG/geometry-allocation overhead.
"""

import numpy as np

cimport numpy as cnp
from libc.math cimport NAN

cnp.import_array()


ctypedef fused real_t:
    float
    double


def clip_masked(
    real_t[:, :] arr,
    double[:, ::1] mask,
    double nodata,
    int has_nodata,
):
    """Gather masked cells into a 1-D array, mapping nodata to ``nan``.

    Reproduces ``var[window][mask == 1]`` followed by the nodata-to-``nan``
    replacement, in a single typed pass and in row-major order.

    Parameters
    ----------
    arr : memoryview
        The window of raster values (``float32`` or ``float64``).
    mask : memoryview[double]
        The footprint mask (non-zero = selected), same shape as ``arr``.
    nodata : double
        The nodata value (ignored when ``has_nodata`` is 0).
    has_nodata : int
        1 to replace ``nodata`` values with ``nan``, 0 to keep raw values.

    Returns
    -------
    numpy.ndarray
        1-D ``float64`` array of the selected values.
    """
    cdef Py_ssize_t h = arr.shape[0]
    cdef Py_ssize_t w = arr.shape[1]
    cdef Py_ssize_t i, j, k = 0
    cdef Py_ssize_t count = 0
    cdef double val

    for j in range(h):
        for i in range(w):
            if mask[j, i] != 0.0:
                count += 1

    cdef cnp.ndarray[cnp.double_t, ndim=1] out = np.empty(count, dtype=np.float64)
    cdef double[::1] o = out

    for j in range(h):
        for i in range(w):
            if mask[j, i] != 0.0:
                val = arr[j, i]
                if has_nodata and val == nodata:
                    val = NAN
                o[k] = val
                k += 1

    return out


cdef inline int _seg_intersects_rect(
    double ax,
    double ay,
    double bx,
    double by,
    double xmin,
    double ymin,
    double xmax,
    double ymax,
) noexcept nogil:
    """Return 1 if segment a-b overlaps the closed rectangle (Liang-Barsky)."""
    cdef double dx = bx - ax
    cdef double dy = by - ay
    cdef double t0 = 0.0
    cdef double t1 = 1.0
    cdef double p, q, r
    cdef int i

    # Degenerate segment (a single point).
    if dx == 0.0 and dy == 0.0:
        return 1 if (xmin <= ax <= xmax and ymin <= ay <= ymax) else 0

    for i in range(4):
        if i == 0:
            p = -dx
            q = ax - xmin
        elif i == 1:
            p = dx
            q = xmax - ax
        elif i == 2:
            p = -dy
            q = ay - ymin
        else:
            p = dy
            q = ymax - ay

        if p == 0.0:
            # Line parallel to this edge; outside the slab means no overlap.
            if q < 0.0:
                return 0
        else:
            r = q / p
            if p < 0.0:
                if r > t1:
                    return 0
                if r > t0:
                    t0 = r
            else:
                if r < t0:
                    return 0
                if r < t1:
                    t1 = r

    return 1 if t0 <= t1 else 0


cdef inline int _point_in_rings(
    double px,
    double py,
    double[::1] xs,
    double[::1] ys,
    int[::1] ring_starts,
    Py_ssize_t n_rings,
) noexcept nogil:
    """Even-odd point-in-polygon over all rings (holes included)."""
    cdef int inside = 0
    cdef Py_ssize_t r, k, start, end
    cdef double xi, yi, xj, yj

    for r in range(n_rings):
        start = ring_starts[r]
        end = ring_starts[r + 1]
        for k in range(start, end - 1):
            xi = xs[k]
            yi = ys[k]
            xj = xs[k + 1]
            yj = ys[k + 1]
            if (yi > py) != (yj > py):
                if px < (xj - xi) * (py - yi) / (yj - yi) + xi:
                    inside ^= 1
    return inside


def cell_mask(
    double[::1] xs,
    double[::1] ys,
    int[::1] ring_starts,
    int is_areal,
    double plx,
    double ply,
    double dx,
    double dy,
    Py_ssize_t px_w,
    Py_ssize_t px_h,
):
    """Build a footprint mask for a window of ``px_w`` x ``px_h`` cells.

    Parameters
    ----------
    xs, ys : memoryview[double]
        Flattened ring/line coordinates of the geometry.
    ring_starts : memoryview[int]
        Offsets into ``xs``/``ys``; ring ``r`` spans
        ``ring_starts[r]:ring_starts[r + 1]``.
    is_areal : int
        1 for polygonal geometries (enables the inside test), 0 otherwise.
    plx, ply : double
        World coordinates of the upper-left cell corner of the window.
    dx, dy : double
        Cell width and height (``dy`` is typically negative).
    px_w, px_h : Py_ssize_t
        Window size in cells.

    Returns
    -------
    numpy.ndarray
        A ``(px_h, px_w)`` float64 mask (1 = covered, 0 = not covered).
    """
    cdef cnp.ndarray[cnp.double_t, ndim=2] mask = np.zeros(
        (px_h, px_w), dtype=np.float64
    )
    cdef double[:, ::1] m = mask
    cdef Py_ssize_t n_rings = ring_starts.shape[0] - 1
    cdef Py_ssize_t i, j, r, k, start, end
    cdef double x0, y0, x1, y1, xmin, ymin, xmax, ymax, cx, cy
    cdef int hit

    if n_rings < 1:
        return mask

    with nogil:
        for j in range(px_h):
            y0 = ply + dy * j
            y1 = y0 + dy
            if y0 < y1:
                ymin = y0
                ymax = y1
            else:
                ymin = y1
                ymax = y0
            for i in range(px_w):
                x0 = plx + dx * i
                x1 = x0 + dx
                if x0 < x1:
                    xmin = x0
                    xmax = x1
                else:
                    xmin = x1
                    xmax = x0

                hit = 0
                for r in range(n_rings):
                    start = ring_starts[r]
                    end = ring_starts[r + 1]
                    for k in range(start, end - 1):
                        if _seg_intersects_rect(
                            xs[k], ys[k], xs[k + 1], ys[k + 1],
                            xmin, ymin, xmax, ymax,
                        ):
                            hit = 1
                            break
                    if hit:
                        break

                if not hit and is_areal:
                    cx = (xmin + xmax) * 0.5
                    cy = (ymin + ymax) * 0.5
                    if _point_in_rings(cx, cy, xs, ys, ring_starts, n_rings):
                        hit = 1

                if hit:
                    m[j, i] = 1.0

    return mask
