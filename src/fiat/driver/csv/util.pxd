"""Utils header."""

cdef bint _is_int_type(object d)
cdef bint _is_float_type(object d)
cdef int _frame_kind(list dtypes)
cdef object _kind_dtype(int kind)
