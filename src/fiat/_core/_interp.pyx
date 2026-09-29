# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
"""Fast 1D linear interpolation"""

import numpy as np

cimport numpy as cnp
from libc.math cimport NAN, isnan

cnp.import_array()


cdef class Interp1D:
    """Linear interpolation object over a monotonically increasing grid.

    Parameters
    ----------
    x : array_like
        The (strictly increasing) sample points.
    y : array_like
        The values at ``x``. Must have the same length as ``x``.
    """

    cdef double[::1] _x
    cdef double[::1] _y
    cdef Py_ssize_t _n

    def __init__(self, x, y):
        cdef cnp.ndarray[cnp.double_t, ndim=1] xa = np.ascontiguousarray(
            x, dtype=np.float64
        )
        cdef cnp.ndarray[cnp.double_t, ndim=1] ya = np.ascontiguousarray(
            y, dtype=np.float64
        )
        if xa.shape[0] != ya.shape[0]:
            raise ValueError("x and y must have the same length")
        if xa.shape[0] < 2:
            raise ValueError("at least two sample points are required")
        self._x = xa
        self._y = ya
        self._n = xa.shape[0]

    cdef double _eval(self, double xq) noexcept nogil:
        cdef Py_ssize_t n = self._n
        cdef Py_ssize_t lo, hi, mid
        cdef double x0, x1, y0, y1

        if isnan(xq):
            return NAN

        # Below the first knot: extrapolate along the first segment.
        if xq <= self._x[0]:
            x0 = self._x[0]
            x1 = self._x[1]
            y0 = self._y[0]
            y1 = self._y[1]
            return y0 + (y1 - y0) * (xq - x0) / (x1 - x0)

        # Above the last knot: extrapolate along the last segment.
        if xq >= self._x[n - 1]:
            x0 = self._x[n - 2]
            x1 = self._x[n - 1]
            y0 = self._y[n - 2]
            y1 = self._y[n - 1]
            return y0 + (y1 - y0) * (xq - x0) / (x1 - x0)

        # Binary search for the interval [lo, lo + 1] containing xq.
        lo = 0
        hi = n - 1
        while hi - lo > 1:
            mid = (lo + hi) >> 1
            if self._x[mid] <= xq:
                lo = mid
            else:
                hi = mid

        x0 = self._x[lo]
        x1 = self._x[lo + 1]
        y0 = self._y[lo]
        y1 = self._y[lo + 1]
        return y0 + (y1 - y0) * (xq - x0) / (x1 - x0)

    def __call__(self, double xq) -> float:
        """Evaluate the interpolation at ``xq``."""
        return self._eval(xq)

    def __reduce__(self):
        # Enable pickling for multiprocessing (e.g. Windows spawn start method).
        return (
            Interp1D,
            (np.asarray(self._x), np.asarray(self._y)),
        )
