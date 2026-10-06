/* FIAT-authored hand-rolled TIFF / GeoTIFF / COG codec.
 *
 * This is a small, self-contained C++ layer (no libtiff / libgeotiff / GDAL)
 * that the Cython reader/writer (`reader.pyx`, `writer.pyx`) use to:
 *   - parse a (classic, little/big-endian) TIFF: header + every IFD, the tile
 *     or strip layout, pixel data type, nodata, GeoTIFF geo-keys and the
 *     GDAL_METADATA per-band tag,
 *   - DEFLATE (zlib) compress / decompress individual tiles,
 *   - assemble a strict Cloud Optimized GeoTIFF (COG) header: a header-first
 *     IFD chain (full resolution followed by the overview pyramid) with correct
 *     TileOffsets / TileByteCounts, GeoKeys and metadata.
 *
 * File positioning, the cross-process write lock, overview down-sampling and
 * all multiprocessing live on the Python/Cython side (mirroring the split used
 * by the FlatGeobuf driver). This layer never opens a file; it only transforms
 * byte buffers.
 *
 * Specifications followed (cited here and at the relevant call sites):
 *   - TIFF 6.0 (Adobe, 1992): header, IFD, tags, tiling, SampleFormat.
 *   - TIFF Technical Note 2: Adobe Deflate (Compression = 8).
 *   - OGC GeoTIFF 1.1 (OGC 19-008r4): ModelPixelScaleTag (33550),
 *     ModelTiepointTag (33922), GeoKeyDirectoryTag (34735),
 *     GeoDoubleParamsTag (34736), GeoAsciiParamsTag (34737), geo-keys
 *     GTModelTypeGeoKey (1024), GTRasterTypeGeoKey (1025),
 *     GeographicTypeGeoKey (2048), ProjectedCSTypeGeoKey (3072),
 *     GTCitationGeoKey (1026) / PCSCitationGeoKey (3073).
 *   - OGC Cloud Optimized GeoTIFF 1.0 (OGC 21-026): header-first IFD layout,
 *     tiled, overviews ordered full-res -> coarsest, ghost-area leader.
 *   - GDAL conventions: GDAL_NODATA tag (42113) as ASCII, GDAL_METADATA tag
 *     (42112) as XML with <Item name=... sample=...> per-band entries.
 *   - zlib manual (compress2 / uncompress), zlib 1.3.
 */
#ifndef FIAT_TIFF_C_H_
#define FIAT_TIFF_C_H_

#include <cstdint>
#include <string>
#include <vector>

namespace fiatgtiff {

// A single GDAL_METADATA <Item> entry (tag 42112). `sample` is the 0-based band
// index the item applies to, or -1 for a dataset-level item.
struct MetaItem {
    std::string name;
    std::string value;
    int sample = -1;
};

// One Image File Directory (one resolution level of the raster).
struct IfdInfo {
    uint32_t width = 0;
    uint32_t height = 0;
    uint32_t tile_width = 0;   // 0 when the IFD is strip-organised
    uint32_t tile_height = 0;  // 0 when the IFD is strip-organised
    uint32_t rows_per_strip = 0;
    uint16_t samples_per_pixel = 1;
    uint16_t bits_per_sample =
        0;                       // per sample (all samples share a width here)
    uint16_t sample_format = 1;  // TIFF tag 339: 1=uint, 2=int, 3=float
    uint16_t compression = 1;    // 1=none, 8=Adobe Deflate
    uint16_t planar_config = 1;  // 1=chunky (interleaved), 2=planar
    uint16_t predictor = 1;      // 1=none, 2=horizontal, 3=float
    uint8_t is_tiled = 0;
    uint8_t is_reduced = 0;  // NewSubfileType (254) bit 0 -> overview level
    std::vector<uint64_t> tile_offsets;     // tile (or strip) byte offsets
    std::vector<uint64_t> tile_bytecounts;  // tile (or strip) byte counts
};

// Everything the reader needs after parsing a whole TIFF file.
struct TiffInfo {
    uint8_t big_endian = 0;
    uint8_t is_bigtiff = 0;
    std::vector<IfdInfo> ifds;  // ifds[0] = full resolution, rest = overviews

    // Georeferencing (taken from the first/full-resolution IFD).
    uint8_t has_pixel_scale = 0;
    double pixel_scale[3] = {0, 0, 0};  // tag 33550: (sx, sy, sz)
    uint8_t has_tiepoint = 0;
    double tiepoint[6] = {0, 0, 0, 0, 0, 0};  // tag 33922: (i,j,k, x,y,z)

    int model_type = 0;  // GTModelTypeGeoKey 1024: 1=projected, 2=geographic
    int raster_type =
        0;  // GTRasterTypeGeoKey 1025: 1=PixelIsArea, 2=PixelIsPoint
    int epsg =
        0;  // ProjectedCSTypeGeoKey (3072) or GeographicTypeGeoKey (2048)
    std::string
        crs_citation;  // GTCitation/PCSCitation geo-key text (WKT fallback)

    uint8_t has_nodata = 0;
    double nodata = 0;  // parsed from GDAL_NODATA (42113)

    std::vector<MetaItem> meta_items;  // parsed from GDAL_METADATA (42112)
};

// Specification used to build a COG. The caller fills geometry, data type, CRS
// (resolved to an EPSG code and/or WKT on the Python side) and per-band
// metadata; the overview pyramid dimensions are supplied explicitly.
struct CogSpec {
    uint32_t width = 0;
    uint32_t height = 0;
    uint32_t tile_width = 256;
    uint32_t tile_height = 256;
    uint16_t samples_per_pixel = 1;
    uint16_t bits_per_sample = 32;
    uint16_t sample_format = 3;  // default float32 output
    uint16_t compression = 8;    // 1=none, 8=deflate
    uint16_t predictor = 1;

    uint8_t has_nodata = 0;
    double nodata = 0;

    uint8_t has_pixel_scale = 0;
    double pixel_scale[3] = {0, 0, 0};
    uint8_t has_tiepoint = 0;
    double tiepoint[6] = {0, 0, 0, 0, 0, 0};

    int model_type = 1;   // 1=projected, 2=geographic
    int raster_type = 1;  // PixelIsArea
    int epsg = 0;         // 0 -> rely on the WKT citation only
    std::string
        crs_citation;  // GTCitation / PCSCitation text (e.g. CRS name or WKT)

    // Per-band metadata written into GDAL_METADATA (tag 42112). The ASCII
    // GDAL_NODATA tag (42113) is formatted from `nodata` on the C++ side (see
    // has_nodata / nodata above), so no pre-formatted strings are passed in.
    std::vector<MetaItem> meta_items;
};

// --- Parsing --------------------------------------------------------------
// Parse a whole TIFF held in `buf`. Returns 1 on success, 0 on failure.
int parse_tiff(const uint8_t* buf, size_t len, TiffInfo& out);

// --- zlib codec -----------------------------------------------------------
// DEFLATE-compress `len` bytes at `data` (zlib wrapper, level in 0..9).
std::string deflate_block(const uint8_t* data, size_t len, int level);

// INFLATE `src_len` bytes at `src` into `dst` (capacity `dst_cap`). Returns the
// number of bytes written, or 0 on failure.
size_t inflate_block(const uint8_t* src, size_t src_len, uint8_t* dst,
                     size_t dst_cap);

// --- COG assembly ---------------------------------------------------------
// Build the complete COG header: the header-first IFD chain for the full
// resolution level (index 0) plus every overview level, with TileOffsets and
// TileByteCounts filled in from the supplied compressed-tile byte sizes.
//
// Inputs:
//   spec                  - raster geometry / dtype / CRS / metadata.
//   level_width/height    - dimensions of each level (level 0 = full res).
//   level_tile_bytecounts - for each level, the byte size of every compressed
//                           tile, in row-major (top-to-bottom, left-to-right)
//                           tile order.
// Outputs:
//   data_start        - absolute byte offset where the first tile is written.
//   tile_offsets_flat - absolute byte offset of every tile, flattened level by
//                       level in the same order as level_tile_bytecounts.
// Returns the header bytes (to be written at offset 0). Tiles are then written
// contiguously starting at data_start in the order of tile_offsets_flat.
std::string build_cog_header(
    const CogSpec& spec, const std::vector<uint32_t>& level_width,
    const std::vector<uint32_t>& level_height,
    const std::vector<std::vector<uint64_t>>& level_tile_bytecounts,
    uint64_t& data_start, std::vector<uint64_t>& tile_offsets_flat);

// Deterministic byte size of the COG header region for the given geometry (the
// absolute offset at which tile data begins). Because the TileOffsets /
// TileByteCounts fields are fixed-width (one LONG per tile), the header size
// depends only on geometry, not on the compressed tile sizes. This lets the
// streaming writer reserve the header up front, append compressed tiles
// directly into the final file, and patch the header afterwards.
uint64_t cog_header_size(const CogSpec& spec,
                         const std::vector<uint32_t>& level_width,
                         const std::vector<uint32_t>& level_height);

// Build the COG header using explicit, per-tile absolute offsets instead of
// assigning them sequentially. Used by the streaming writer where tiles are
// appended to the file as they are produced (and so are not in tile order).
// The returned header is padded to cog_header_size(spec, ...) bytes.
std::string build_cog_header_fixed(
    const CogSpec& spec, const std::vector<uint32_t>& level_width,
    const std::vector<uint32_t>& level_height,
    const std::vector<std::vector<uint64_t>>& level_tile_offsets,
    const std::vector<std::vector<uint64_t>>& level_tile_bytecounts);

// Build the single-IFD block of a plain (non-COG) tiled GeoTIFF, to be appended
// at `ifd_block_start` (the end of the already-written tile data). Classic TIFF
// allows the IFD to live anywhere, so the writer streams tiles first and writes
// this IFD last. The caller writes the 8-byte TIFF header separately with its
// first-IFD pointer set to `ifd_block_start`. `tile_offsets` /
// `tile_bytecounts` are the absolute offsets and byte sizes of the tiles in
// row-major order.
std::string build_plain_ifd(const CogSpec& spec, uint32_t width,
                            uint32_t height,
                            const std::vector<uint64_t>& tile_offsets,
                            const std::vector<uint64_t>& tile_bytecounts,
                            uint64_t ifd_block_start);

// --- Tile pack / overview down-sampling -----------------------------------
// Pad a chunky (src_h, src_w, spp) source to a full (tile_h, tile_w) tile with
// `nodata`, then DEFLATE it (compression 8) or leave it raw. `sample_format` /
// `bits` give the pixel dtype (1=uint, 2=int, 3=float).
std::string encode_tile(const uint8_t* src, uint32_t src_h, uint32_t src_w,
                        uint32_t tile_w, uint32_t tile_h, uint16_t spp,
                        uint16_t sample_format, uint16_t bits, double nodata,
                        uint8_t has_nodata, uint16_t compression, int level);

// Down-sample a chunky (src_h, src_w, spp) block by two (nodata-aware average
// for float, decimation otherwise), pad the result to a (tile_h, tile_w) tile
// and encode it like encode_tile. Used to build the COG overview pyramid.
std::string downsample_tile(const uint8_t* src, uint32_t src_h, uint32_t src_w,
                            uint32_t tile_w, uint32_t tile_h, uint16_t spp,
                            uint16_t sample_format, uint16_t bits,
                            double nodata, uint8_t has_nodata,
                            uint16_t compression, int level);

// Down-sample a chunky (src_h, src_w, spp) block by two into a raw (no pad, no
// compression) chunky buffer of size (out_h, out_w, spp); sets out_h/out_w.
// Used to assemble deeper overview levels a quadrant at a time without a large
// scratch block.
std::string downsample_raw(const uint8_t* src, uint32_t src_h, uint32_t src_w,
                           uint16_t spp, uint16_t sample_format, uint16_t bits,
                           double nodata, uint8_t has_nodata, uint32_t& out_h,
                           uint32_t& out_w);

}  // namespace fiatgtiff

#endif  // FIAT_TIFF_C_H_
