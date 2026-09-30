/* FIAT-authored C++ helper layer over the vendored FlatGeobuf sources.
 *
 * Provides a small, Cython-friendly API for:
 *   - building / parsing the FlatGeobuf Header flatbuffer,
 *   - building / parsing per-feature Geometry + raw property bytes,
 *   - packed Hilbert R-tree ordering, index building and bbox search.
 *
 * Geometry is exchanged in a flat representation:
 *   xy    : interleaved x,y coordinates (2 doubles per point)
 *   ends  : cumulative coordinate-PAIR counts at the end of each ring/line
 *   parts : cumulative ring counts at the end of each polygon (MultiPolygon
 * only) For Point / MultiPoint / LineString: ends and parts are empty. For
 * Polygon / MultiLineString: ends set, parts empty. For MultiPolygon: both ends
 * (global over all rings) and parts set.
 */
#ifndef FIAT_FGB_C_H_
#define FIAT_FGB_C_H_

#include <cstdint>
#include <string>
#include <vector>

namespace fiatfgb {

// Plain result struct filled by parse_header (mirrors the FlatGeobuf Header).
struct HeaderResult {
    std::string name;                    // Layer name.
    uint8_t geometry_type = 0;           // FlatGeobuf GeometryType code.
    uint64_t features_count = 0;         // Number of features in the file.
    uint16_t index_node_size = 16;       // R-tree node size (0 = no index).
    std::vector<std::string> col_names;  // Attribute column names.
    std::vector<uint8_t> col_types;      // Attribute column type codes.
    std::string crs_wkt;                 // CRS as WKT (optional).
    std::string crs_org;                 // CRS authority name, e.g. "EPSG".
    int32_t crs_code = 0;                // CRS authority code, e.g. 4326.
    uint8_t has_envelope = 0;            // 1 if a layer envelope is present.
    // Layer envelope (bounding box) when has_envelope == 1.
    double env_minx = 0, env_miny = 0, env_maxx = 0, env_maxy = 0;
};

// Flat geometry produced by parse_feature (see the layout notes at the top).
struct GeometryResult {
    uint8_t geometry_type = 0;    // FlatGeobuf GeometryType code.
    std::vector<double> xy;       // Interleaved x, y coordinates.
    std::vector<uint32_t> ends;   // Cumulative coordinate-pair count per ring.
    std::vector<uint32_t> parts;  // Cumulative ring count per polygon.
    double minx = 0, miny = 0, maxx = 0, maxy = 0;  // Bounding box.
    uint8_t empty = 1;  // 1 if the geometry has no coordinates.
};

// --- Header ---------------------------------------------------------------
// Build a size-prefixed Header flatbuffer (without magic bytes).
std::string build_header(const std::string& name, uint8_t geometry_type,
                         const std::vector<std::string>& col_names,
                         const std::vector<uint8_t>& col_types,
                         uint64_t features_count, uint16_t index_node_size,
                         uint8_t has_envelope, double minx, double miny,
                         double maxx, double maxy, const std::string& crs_org,
                         int32_t crs_code, const std::string& crs_wkt);

// Parse a size-prefixed Header at buf. Returns bytes consumed (prefix + body),
// or 0 on failure.
size_t parse_header(const uint8_t* buf, size_t len, HeaderResult& out);

// --- Feature --------------------------------------------------------------
// Build a size-prefixed Feature flatbuffer from a flat geometry + raw props.
std::string build_feature(uint8_t geom_type, const std::vector<double>& xy,
                          const std::vector<uint32_t>& ends,
                          const std::vector<uint32_t>& parts,
                          const std::vector<uint8_t>& props);

// Parse a size-prefixed Feature at buf. Fills geometry and copies raw property
// bytes into out_props. Returns bytes consumed (prefix + body), or 0 on
// failure.
size_t parse_feature(const uint8_t* buf, size_t len, GeometryResult& geom,
                     std::string& out_props);

// --- Packed Hilbert R-tree ------------------------------------------------
// Given per-feature envelopes (env = 4*N: minx,miny,maxx,maxy), return the
// feature indices in Hilbert order and fill extent[4].
std::vector<uint64_t> hilbert_order(const std::vector<double>& env,
                                    double extent[4]);

// Build the packed R-tree index bytes. env_ordered (4*N) and offsets (N) must
// already be in Hilbert order; offsets are byte offsets of each feature within
// the feature data section.
std::string build_index(const std::vector<double>& env_ordered,
                        const std::vector<uint64_t>& offsets,
                        const double extent[4], uint16_t node_size);

// Search the packed R-tree stored in data; returns matching feature byte
// offsets (into the feature data section).
std::vector<uint64_t> search_index(const uint8_t* data, size_t data_len,
                                   uint64_t num_items, uint16_t node_size,
                                   double minx, double miny, double maxx,
                                   double maxy);

// Serialized byte size of the index for num_items / node_size.
uint64_t index_size(uint64_t num_items, uint16_t node_size);

}  // namespace fiatfgb

#endif  // FIAT_FGB_C_H_
