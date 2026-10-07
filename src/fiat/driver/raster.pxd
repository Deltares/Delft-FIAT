# cython: language_level=3
"""Declarations for the shared raster spatial-metadata structure."""

cdef class GridProfile:
    cdef public object crs_wkt
    cdef public object xvals
    cdef public object yvals
    cdef public object res
    cdef public object origin
    cdef public object transform
    cdef public object bounds
    cdef public object shape
    cdef public object shape_xy

    cpdef derive_from_dims(self)
