# cython: language_level=3
"""Shared declarations for the hand-rolled GeoTIFF driver.

Exposes the C++ codec layer (``tiff_c.h``) so the reader and writer modules can
``cimport`` the parse/build/zlib primitives. See ``tiff_c.h`` for the file-format
specifications these mirror.
"""

from libc.stdint cimport uint8_t, uint16_t, uint32_t, uint64_t
from libcpp.string cimport string
from libcpp.vector cimport vector


cdef extern from "tiff_c.h" namespace "fiatgtiff":
    cdef cppclass MetaItem:
        string name
        string value
        int sample

    cdef cppclass IfdInfo:
        uint32_t width
        uint32_t height
        uint32_t tile_width
        uint32_t tile_height
        uint32_t rows_per_strip
        uint16_t samples_per_pixel
        uint16_t bits_per_sample
        uint16_t sample_format
        uint16_t compression
        uint16_t planar_config
        uint16_t predictor
        uint8_t is_tiled
        uint8_t is_reduced
        vector[uint64_t] tile_offsets
        vector[uint64_t] tile_bytecounts

    cdef cppclass TiffInfo:
        uint8_t big_endian
        uint8_t is_bigtiff
        vector[IfdInfo] ifds
        uint8_t has_pixel_scale
        double pixel_scale[3]
        uint8_t has_tiepoint
        double tiepoint[6]
        int model_type
        int raster_type
        int epsg
        string crs_citation
        uint8_t has_nodata
        double nodata
        vector[MetaItem] meta_items

    cdef cppclass CogSpec:
        uint32_t width
        uint32_t height
        uint32_t tile_width
        uint32_t tile_height
        uint16_t samples_per_pixel
        uint16_t bits_per_sample
        uint16_t sample_format
        uint16_t compression
        uint16_t predictor
        uint8_t has_nodata
        double nodata
        uint8_t has_pixel_scale
        double pixel_scale[3]
        uint8_t has_tiepoint
        double tiepoint[6]
        int model_type
        int raster_type
        int epsg
        string crs_citation
        string gdal_nodata_ascii
        string gdal_metadata_xml

    int parse_tiff(const uint8_t* buf, size_t length, TiffInfo& out) except +

    string deflate_block(const uint8_t* data, size_t length, int level) except +

    size_t inflate_block(const uint8_t* src, size_t src_len, uint8_t* dst,
                         size_t dst_cap) except +

    string build_cog_header(const CogSpec& spec,
                            const vector[uint32_t]& level_width,
                            const vector[uint32_t]& level_height,
                            const vector[vector[uint64_t]]& level_tile_bytecounts,
                            uint64_t& data_start,
                            vector[uint64_t]& tile_offsets_flat) except +
