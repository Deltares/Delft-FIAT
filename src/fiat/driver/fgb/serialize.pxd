"""Cython header files for serialization."""

from libc.stdint cimport uint8_t

# --- Property (attribute) codec -------------------------------------------
cdef bytes _bytes_from_ptr(const uint8_t* p, size_t n)
cdef object _decode_properties(const uint8_t* p, size_t n, list col_types)
cdef bytes _encode_properties(list values, list col_types)
