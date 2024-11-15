# cython: cdivision=True
# cython: boundscheck=False
# cython: nonecheck=False
# cython: wraparound=False
import numpy as np
cimport numpy as cnp

from fiat.gis._util cimport world2pixel

cnp.import_array()


cdef cnp.ndarray[cnp.int8_t, ndim=2] polygon_corners(
    cnp.ndarray[cnp.float64_t, ndim=3] x,
    cnp.ndarray[cnp.float64_t, ndim=3] y,
    cnp.ndarray[cnp.float64_t, ndim=2] geometry,
    Py_ssize_t n,
    Py_ssize_t z,
    Py_ssize_t h,
    Py_ssize_t w,
):
    """Rasterize a polygon according to the even odd rule.

    This function focusses on the corners of the cells.
    This means that in- and output are 3d matrices.

    Parameters
    ----------
    x : np.ndarray[np.float64_t, ndim=3]
        A 3D array of the x coordinates of the raster.
    y : np.ndarray[np.float64_t, ndim=3]
        A 3D array of the y coordinates of the raster.
    geometry : list | tuple,
        A list or tuple containing tuples of xy coordinates of the vertices.

    Returns
    -------
    np.ndarray[np.bool_, ndim=3]
        The resulting binary rasterized polygon.
    """
    cdef int i
    cdef int d1, d2, d3
    cdef double p1x, p1y, p2x, p2y, xinters
    cdef cnp.ndarray[cnp.int8_t, ndim=3, cast=True] touched
    cdef cnp.ndarray[cnp.int8_t, ndim=3, cast=True] mask

    touched = np.zeros((z, h, w), dtype=np.bool_)
    mask = np.zeros((z, h, w), dtype=np.bool_)

    p1x, p1y = geometry[0]

    for i in range(n + 1):
        p2x, p2y = geometry[i % n]

        for d1 in range(z):
            for d2 in range(h):
                for d3 in range(w):
                    if ((y[d1, d2, d3] >= min(p1y, p2y))
                        and (y[d1, d2, d3] <= max(p1y, p2y))
                            and (x[d1, d2, d3] <= max(p1x, p2x))):
                        if p1y != p2y:
                            xinters = ((y[d1, d2, d3] - p1y)
                                       * (p2x - p1x) / (p2y - p1y) + p1x)
                            if (p1x == p2x) or (x[d1, d2, d3] <= xinters):
                                mask[d1, d2, d3] = True
                        else:
                            mask[d1, d2, d3] = True
                    else:
                        mask[d1, d2, d3] = False

        touched ^= mask
        p1x, p1y = p2x, p2y

    return touched


cdef cnp.ndarray[cnp.int8_t, ndim=2] polygon_vertices(
    cnp.ndarray[cnp.int8_t, ndim=2, cast=True] mask,
    cnp.ndarray[cnp.float64_t, ndim=2] xmin,
    cnp.ndarray[cnp.float64_t, ndim=2] xmax,
    cnp.ndarray[cnp.float64_t, ndim=2] ymin,
    cnp.ndarray[cnp.float64_t, ndim=2] ymax,
    cnp.ndarray[cnp.float64_t, ndim=2] geometry,
    Py_ssize_t n,
    Py_ssize_t h,
    Py_ssize_t w,
):
    """_summary_."""
    cdef int i, d1, d2
    cdef double px, py

    for i in range(n):
        px, py = geometry[i % n]
        for j in range(h):
            for k in range(w):
                if ((px > xmin[j, k]) and (px < xmax[j, k])
                    and (py > ymin[j, k]) and (py < ymax[j, k])):
                    mask[j, k] = 1
    return mask


cpdef cnp.ndarray[cnp.int8_t, ndim=2] polygon_all_touched(
    cnp.ndarray[cnp.float64_t, ndim=3] x,
    cnp.ndarray[cnp.float64_t, ndim=3] y,
    cnp.ndarray[cnp.float64_t, ndim=2] geometry,
):
    """_summary_."""
    cdef cnp.ndarray[cnp.int8_t, ndim=3, cast=True] touched
    cdef cnp.ndarray[cnp.int8_t, ndim=2, cast=True] mask
    cdef Py_ssize_t z, h, w
    cdef Py_ssize_t n
    cdef int d1, d2, d3

    n = geometry.shape[0]
    z = x.shape[0]
    h = x.shape[1]
    w = x.shape[2]

    touched = polygon_corners(
        x=x, y=y, geometry=geometry, n=n, z=z, h=h, w=w,
    )
    mask = np.zeros((h, w), dtype=np.bool_)

    for d2 in range(h):
        for d3 in range(w):
            for d1 in range(z):
                if touched[d1, d2, d3]:
                    mask[d2, d3] = True
                    break

    mask = polygon_vertices(
        mask=mask,
        xmin=x[0],
        xmax=x[1],
        ymin=y[2],
        ymax=y[0],
        geometry=geometry,
        n=n,
        h=h,
        w=w,
    )

    return mask


cpdef polyline(
    cnp.ndarray[cnp.float64_t, ndim=2] geometry,
    Py_ssize_t ulX,
    Py_ssize_t ulY,
    Py_ssize_t lrX,
    Py_ssize_t lrY,
    tuple gtf,
):
    """_summary_."""
    cdef cnp.ndarray[cnp.int8_t, ndim=2, cast=True] mask
    cdef int h, w, d1, d2
    h = lrY - ulY
    w = lrX - ulX
    mask = np.zeros((h, w), dtype=np.bool_)
    cdef Py_ssize_t n, p1x, p1y, p2x, p2y
    cdef int c0, r0, c1, r1
    cdef int i

    n = geometry.shape[0]
    p1x, p1y = geometry[0]
    c0, r0 = world2pixel(p1x, p1y, gtf)

    cdef char steep = 0
    cdef int r = r0
    cdef int c = c0
    cdef int sr, sc, d
    cdef Py_ssize_t dc, dr

    for i in range(1, n):
        p2x, p2y = geometry[i % n]
        c1, r1 = world2pixel(p2x, p2y, gtf)
        steep = 0
        dr = abs(r1 - r0)
        dc = abs(c1 - c0)

        if (c1 - c) > 0:
            sc = 1
        else:
            sc = -1
        if (r1 - r) > 0:
            sr = 1
        else:
            sr = -1
        if dr > dc:
            steep = 1
            c, r = r, c
            dc, dr = dr, dc
            sc, sr = sr, sc
        d = (2 * dr) - dc

        for d1 in range(h):
            for d2 in range(w):
                if steep:
                    mask[c,r] = True
                else:
                    mask[r,c] = True
                while d >= 0:
                    r = r + sr
                    d = d - (2 * dc)
                c = c + sc
                d = d + (2 * dr)

        mask[r1, c1] = True

    return mask
