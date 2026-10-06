"""Table header file."""

cdef class Table:
    cdef public object data
    cdef public list dtypes
    cdef public object duplicate_columns
    cdef dict _columns
    cdef object _labels
    cdef dict _lookup
    cdef str _index_name

    cdef Py_ssize_t _row_pos(self, object label) except -1
    cdef void _set_columns(self, columns)
