# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
"""Fast 1D linear and nD multilinear interpolation."""

from libc.math cimport NAN, isnan

import numpy as np

cimport numpy as cnp

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

    def __call__(self, xq):
        """Evaluate the interpolation at ``xq``.

        Accepts a Python scalar (returns a ``float``) or an array-like (returns
        a ``float64`` ``numpy.ndarray`` of the same shape). This mirrors the
        ``scipy`` spline it replaces, so it is a drop-in for both the geometry
        model (scalar calls) and the grid model (array calls).

        Parameters
        ----------
        xq : float or array_like
            Query locations.

        Returns
        -------
        float or numpy.ndarray
            Interpolated values at ``xq``.
        """
        if isinstance(xq, (int, float)):
            return self._eval(xq)

        cdef cnp.ndarray xa = np.ascontiguousarray(xq, dtype=np.float64)
        cdef cnp.ndarray out = np.empty_like(xa)
        cdef double[::1] iv = xa.reshape(-1)
        cdef double[::1] ov = out.reshape(-1)
        cdef Py_ssize_t k, n = iv.shape[0]
        with nogil:
            for k in range(n):
                ov[k] = self._eval(iv[k])
        return out

    def __reduce__(self):
        """Return the reconstruction tuple used by ``pickle``.

        Returns
        -------
        tuple
            Callable and arguments needed to reconstruct the interpolation.
        """
        return (
            Interp1D,
            (np.asarray(self._x), np.asarray(self._y)),
        )

    cdef double _eval(self, double xq) noexcept nogil:
        cdef Py_ssize_t n = self._n
        cdef Py_ssize_t lo, hi, mid
        cdef double x0, x1, y0, y1

        if isnan(xq):
            return NAN

        # Outside the grid: hold the boundary value, like numpy.interp. A
        # vulnerability curve is only defined between its first and last depth;
        # extrapolating along the end segments gives negative damage below the
        # first depth and damage above the last curve value beyond it.
        if xq <= self._x[0]:
            return self._y[0]
        if xq >= self._x[n - 1]:
            return self._y[n - 1]

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


cdef enum:
    MAX_DIMS = 16


cdef class InterpND:
    """Multilinear interpolation object over a rectilinear grid.

    Parameters
    ----------
    axes : Sequence[array_like]
        The (strictly increasing) sample points per axis, at least two axes.
    values : array_like
        The values on the grid, its shape equal to the lengths of ``axes``.
    """

    cdef double[::1] _ax
    cdef double[::1] _v
    cdef Py_ssize_t _d
    cdef Py_ssize_t[::1] _len
    cdef Py_ssize_t[::1] _off
    cdef Py_ssize_t[::1] _stride
    cdef object _axes
    cdef object _values

    def __init__(self, axes, values):
        axes = [np.ascontiguousarray(item, dtype=np.float64) for item in axes]
        va = np.ascontiguousarray(values, dtype=np.float64)
        cdef Py_ssize_t d = len(axes)
        cdef Py_ssize_t k
        if d < 2:
            raise ValueError("at least two axes are required")
        if d > MAX_DIMS:
            raise ValueError(f"at most {MAX_DIMS} axes are supported")
        if va.ndim != d:
            raise ValueError("the number of axes must equal the values dimensions")
        for k in range(d):
            if axes[k].ndim != 1 or axes[k].shape[0] != va.shape[k]:
                raise ValueError(
                    f"length of axis {k} must equal the values dimension {k}"
                )
            if axes[k].shape[0] < 2:
                raise ValueError("at least two sample points per axis are required")

        self._d = d
        self._axes = axes
        self._values = va
        self._ax = np.concatenate(axes)
        self._v = va.reshape(-1)
        lengths = [item.shape[0] for item in axes]
        self._len = np.array(lengths, dtype=np.intp)
        self._off = np.array(
            [sum(lengths[:k]) for k in range(d)], dtype=np.intp
        )
        self._stride = np.array(
            [stride // va.itemsize for stride in va.strides], dtype=np.intp
        )

    def __call__(self, *xq):
        """Evaluate the interpolation at ``xq``.

        Accepts one Python scalar per axis (returns a ``float``) or one
        array-like per axis, all of the same shape (returns a ``float64``
        ``numpy.ndarray`` of that shape).

        Parameters
        ----------
        *xq : float or array_like
            Query locations, one per axis.

        Returns
        -------
        float or numpy.ndarray
            Interpolated values at ``xq``.
        """
        cdef double buf[MAX_DIMS]
        cdef Py_ssize_t k, i, n
        cdef Py_ssize_t d = self._d
        if len(xq) != d:
            raise ValueError(f"expected {d} query arguments, got {len(xq)}")

        if all(isinstance(item, (int, float)) for item in xq):
            for k in range(d):
                buf[k] = xq[k]
            return self._eval(buf)

        arrs = np.broadcast_arrays(
            *[np.asarray(item, dtype=np.float64) for item in xq]
        )
        shape = arrs[0].shape
        cdef double[:, ::1] qv = np.ascontiguousarray(
            np.stack([item.reshape(-1) for item in arrs])
        )
        n = qv.shape[1]
        cdef cnp.ndarray out = np.empty(n, dtype=np.float64)
        cdef double[::1] ov = out
        with nogil:
            for i in range(n):
                for k in range(d):
                    buf[k] = qv[k, i]
                ov[i] = self._eval(buf)
        return out.reshape(shape)

    def __reduce__(self):
        """Return the reconstruction tuple used by ``pickle``.

        Returns
        -------
        tuple
            Callable and arguments needed to reconstruct the interpolation.
        """
        return (InterpND, (self._axes, self._values))

    cdef double _eval(self, double* xq) noexcept nogil:
        cdef Py_ssize_t idx[MAX_DIMS]
        cdef double frac[MAX_DIMS]
        cdef Py_ssize_t d = self._d
        cdef Py_ssize_t k, n, off, lo, hi, mid, c, pos
        cdef double x, x0, x1, w, out

        # Locate the cell and the fraction within it per axis
        for k in range(d):
            x = xq[k]
            if isnan(x):
                return NAN
            n = self._len[k]
            off = self._off[k]
            # Outside the grid: clamp to the boundary (like Interp1D)
            if x <= self._ax[off]:
                idx[k] = 0
                frac[k] = 0.0
                continue
            if x >= self._ax[off + n - 1]:
                idx[k] = n - 2
                frac[k] = 1.0
                continue
            lo = 0
            hi = n - 1
            while hi - lo > 1:
                mid = (lo + hi) >> 1
                if self._ax[off + mid] <= x:
                    lo = mid
                else:
                    hi = mid
            x0 = self._ax[off + lo]
            x1 = self._ax[off + lo + 1]
            idx[k] = lo
            frac[k] = (x - x0) / (x1 - x0)

        # Weighted sum over the 2^d corners of the cell
        out = 0.0
        for c in range(1 << d):
            w = 1.0
            pos = 0
            for k in range(d):
                if (c >> k) & 1:
                    w *= frac[k]
                    pos += (idx[k] + 1) * self._stride[k]
                else:
                    w *= 1.0 - frac[k]
                    pos += idx[k] * self._stride[k]
            if w != 0.0:
                out += w * self._v[pos]
        return out
