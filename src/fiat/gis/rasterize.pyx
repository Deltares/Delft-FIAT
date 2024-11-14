# cython: cdivision=True
# cython: boundscheck=False
# cython: nonecheck=False
# cython: wraparound=False
import numpy as np
cimport numpy as cnp

cnp.import_array()


cpdef rasterize(
    cnp.ndarray[cnp.float64_t, ndim=3] x,
    cnp.ndarray[cnp.float64_t, ndim=3] y,
    list geometry,
):
    """Rasterize a polygon according to the even odd rule.

    Depending on the input, it is either 'center only' or 'all touched'.

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
    cdef Py_ssize_t n
    cdef Py_ssize_t h, w, z
    cdef int d1, d2, d3
    cdef double p1x, p1y, p2x, p2y, xinters
    cdef cnp.ndarray[cnp.int8_t, ndim=3, cast=True] touched
    cdef cnp.ndarray[cnp.int8_t, ndim=3, cast=True] mask

    n = len(geometry)
    h = x.shape[1]
    w = x.shape[2]
    z = x.shape[0]

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


cpdef vertices(
    cnp.ndarray[cnp.int8_t, ndim=2, cast=True] mask,
    cnp.ndarray[cnp.float64_t, ndim=2] xmin,
    cnp.ndarray[cnp.float64_t, ndim=2] xmax,
    cnp.ndarray[cnp.float64_t, ndim=2] ymin,
    cnp.ndarray[cnp.float64_t, ndim=2] ymax,
    cnp.ndarray[cnp.float64_t, ndim=2] geometry,
):
    """_summary_."""
    cdef cnp.ndarray[cnp.float64_t, ndim=1] px
    cdef cnp.ndarray[cnp.float64_t, ndim=1] py
    px = geometry[:, 0]
    py = geometry[:, 1]
    mask |= np.any(
        (
            (px[:, None, None] > xmin)
            & (px[:, None, None] < xmax)
            & (py[:, None, None] > ymin)
            & (py[:, None, None] < ymax)
        ),
        axis=0,
    )
    return mask
