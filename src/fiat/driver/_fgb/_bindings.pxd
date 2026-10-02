# cython: language_level=3
"""Shared declarations for the FlatGeobuf driver.

Exposes the vendored C++ helper layer (``fgb_c.h``) and the low-level attribute
codec so the reader and writer modules can ``cimport`` them.
"""

from libc.stdint cimport int32_t, uint16_t, uint32_t, uint64_t, uint8_t
from libcpp.string cimport string
from libcpp.vector cimport vector

# --- C++ helper layer -----------------------------------------------------
cdef extern from "fgb_c.h" namespace "fiatfgb":
    cdef cppclass HeaderResult:
        string name
        uint8_t geometry_type
        uint64_t features_count
        uint16_t index_node_size
        vector[string] col_names
        vector[uint8_t] col_types
        string crs_wkt
        string crs_org
        int32_t crs_code
        uint8_t has_envelope
        double env_minx
        double env_miny
        double env_maxx
        double env_maxy

    cdef cppclass GeometryResult:
        uint8_t geometry_type
        vector[double] xy
        vector[uint32_t] ends
        vector[uint32_t] parts
        double minx
        double miny
        double maxx
        double maxy
        uint8_t empty

    string build_header(const string& name, uint8_t geometry_type,
                        const vector[string]& col_names,
                        const vector[uint8_t]& col_types,
                        uint64_t features_count, uint16_t index_node_size,
                        uint8_t has_envelope, double minx, double miny,
                        double maxx, double maxy, const string& crs_org,
                        int32_t crs_code, const string& crs_wkt) except +

    size_t parse_header(const uint8_t* buf, size_t length, HeaderResult& out) except +

    string build_feature(uint8_t geom_type, const vector[double]& xy,
                         const vector[uint32_t]& ends,
                         const vector[uint32_t]& parts,
                         const vector[uint8_t]& props) except +

    size_t parse_feature(const uint8_t* buf, size_t length,
                         GeometryResult& geom, string& out_props) except +

    vector[uint64_t] hilbert_order(const vector[double]& env, double* extent) except +

    string build_index(const vector[double]& env_ordered,
                       const vector[uint64_t]& offsets, const double* extent,
                       uint16_t node_size) except +

    vector[uint64_t] search_index(const uint8_t* data, size_t data_len,
                                  uint64_t num_items, uint16_t node_size,
                                  double minx, double miny, double maxx,
                                  double maxy) except +

    uint64_t index_size(uint64_t num_items, uint16_t node_size) except +
