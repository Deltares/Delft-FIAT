"""Helper functions"""

import numpy as np

# Dtype helpers
cdef bint _is_int_type(object d):
    """Whether a python/numpy type is integer like."""
    return d is int or (isinstance(d, type) and issubclass(d, np.integer))


cdef bint _is_float_type(object d):
    """Whether a python/numpy type is float like."""
    return d is float or (isinstance(d, type) and issubclass(d, np.floating))


# Other helpers
cdef int _frame_kind(list dtypes):
    """Pick a backing storage: 1 = int64, 2 = float64, 0 = object."""
    cdef bint all_int = True
    for d in dtypes:
        if _is_int_type(d):
            continue
        all_int = False
        if not _is_float_type(d):
            return 0
    return 1 if all_int else 2

cdef object _kind_dtype(int kind):
    """Translate a storage kind to a numpy dtype."""
    if kind == 1:
        return np.int64
    if kind == 2:
        return np.float64
    return object
