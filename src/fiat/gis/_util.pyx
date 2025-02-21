# cython: cdivision=True
# cython: boundscheck=False
# cython: nonecheck=False
# cython: wraparound=False
# _util.pxd
from libc.math cimport floor


cpdef world2pixel(
    double x,
    double y,
    tuple gtf,
):
    """_summary_."""
    cdef int coorX, coorY
    cdef double ulX, ulY, xDist, yDist

    ulX = gtf[0]
    ulY = gtf[3]
    xDist = gtf[1]
    yDist = gtf[5]
    coorX = <int>floor((x - ulX) / xDist)
    coorY = <int>floor((y - ulY) / yDist)

    return coorX, coorY


cpdef pixel2world(
    int x,
    int y,
    tuple gtf,
):
    """_summary_."""
    pass
