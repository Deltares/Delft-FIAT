# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
"""Fast zonal reduction of clipped hazard values.

``zonal_reduce`` fuses the "filter positive values, then reduce" step used by
the flood hazard functions into a single typed pass over the clipped array
(``nan`` values are treated as non-positive and skipped, matching the previous
``[n for n in hazard if n > 0]`` behaviour). An optional ``sub`` value is
subtracted from every element before the positivity test, which lets the flood
*level* method reuse the same routine (``sub`` = surface reference).
"""

from libc.math cimport NAN

# Reduction method codes (kept in sync with ``fiat.method.util.ZONAL_CODES``).
MEAN = 0
MAX = 1
MIN = 2


def zonal_reduce(double[::1] arr, int method, double sub):
    """Filter positive (``value - sub``) entries and reduce them.

    Parameters
    ----------
    arr : memoryview[double]
        The clipped hazard values (may contain ``nan``).
    method : int
        0 = mean, 1 = max, 2 = min.
    sub : double
        Value subtracted from each element before the positivity test and the
        reduction (0 for the flood depth method).

    Returns
    -------
    tuple
        ``(value, redf)`` where ``value`` is the reduced hazard and ``redf`` is
        the fraction of positive cells. Returns ``(nan, nan)`` when no positive
        cell is found.
    """
    cdef Py_ssize_t n = arr.shape[0]
    cdef Py_ssize_t k
    cdef Py_ssize_t count = 0
    cdef double v
    cdef double acc = 0.0
    cdef double best = 0.0

    for k in range(n):
        v = arr[k] - sub
        if v > 0.0:
            if count == 0:
                best = v
                acc = v
            else:
                acc += v
                if method == MAX:
                    if v > best:
                        best = v
                elif method == MIN:
                    if v < best:
                        best = v
            count += 1

    if count == 0:
        return (NAN, NAN)

    if method == MEAN:
        return (acc / count, <double>count / n)
    return (best, <double>count / n)
