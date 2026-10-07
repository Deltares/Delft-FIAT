# cython: language_level=3
"""Declarations for the shared vector spatial-metadata structure."""

cdef class VectorProfile:
    cdef public object crs_wkt
    cdef public object crs_org
    cdef public object crs_code
    cdef public object crs_override
    cdef public object bounds
    cdef public object geom_type
    cdef public object name
    cdef public object fields
    cdef public object dtypes
    cdef public object columns
    cdef public object size
