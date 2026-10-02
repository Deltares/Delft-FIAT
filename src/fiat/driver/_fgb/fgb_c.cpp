/* FIAT-authored C++ helper layer over the vendored FlatGeobuf sources. */
#include "fgb_c.h"

#include <algorithm>
#include <cstring>
#include <functional>
#include <numeric>

#include "feature_generated.h"
#include "header_generated.h"
#include "packedrtree.h"

namespace fiatfgb {

using namespace FlatGeobuf;

// --- Header ---------------------------------------------------------------
std::string build_header(const std::string& name, uint8_t geometry_type,
                         const std::vector<std::string>& col_names,
                         const std::vector<uint8_t>& col_types,
                         uint64_t features_count, uint16_t index_node_size,
                         uint8_t has_envelope, double minx, double miny,
                         double maxx, double maxy, const std::string& crs_org,
                         int32_t crs_code, const std::string& crs_wkt) {
    // Every FlatBuffer is assembled into a single builder/arena.
    flatbuffers::FlatBufferBuilder fbb;

    // Build the column definitions (name + type) of the attribute table.
    std::vector<flatbuffers::Offset<Column>> cols;
    cols.reserve(col_names.size());
    for (size_t i = 0; i < col_names.size(); ++i) {
        cols.push_back(CreateColumnDirect(
            fbb, col_names[i].c_str(), static_cast<ColumnType>(col_types[i])));
    }
    auto cols_off = fbb.CreateVector(cols);

    // Build the CRS table, but only when some CRS info was actually supplied.
    flatbuffers::Offset<Crs> crs_off = 0;
    if (!crs_wkt.empty() || !crs_org.empty() || crs_code != 0) {
        crs_off = CreateCrsDirect(
            fbb, crs_org.empty() ? nullptr : crs_org.c_str(), crs_code, nullptr,
            nullptr, crs_wkt.empty() ? nullptr : crs_wkt.c_str(), nullptr);
    }

    // Build the layer envelope (bounding box) when requested.
    flatbuffers::Offset<flatbuffers::Vector<double>> env_off = 0;
    if (has_envelope) {
        std::vector<double> env = {minx, miny, maxx, maxy};
        env_off = fbb.CreateVector(env);
    }

    // Strings must be created before the table that references them.
    auto name_off = fbb.CreateString(name);

    // Assemble the Header table field by field.
    HeaderBuilder hb(fbb);
    hb.add_name(name_off);
    if (has_envelope) hb.add_envelope(env_off);
    hb.add_geometry_type(static_cast<GeometryType>(geometry_type));
    hb.add_columns(cols_off);
    hb.add_features_count(features_count);
    // index_node_size > 0 signals that a packed R-tree follows the header.
    hb.add_index_node_size(index_node_size);
    if (crs_off.o != 0) hb.add_crs(crs_off);
    auto header = hb.Finish();
    // Size-prefixed: the 4-byte length precedes the body so the reader can skip
    // straight to the feature section.
    fbb.FinishSizePrefixed(header);

    // Return the raw bytes (prefix + body) as a std::string for the caller.
    return std::string(reinterpret_cast<const char*>(fbb.GetBufferPointer()),
                       fbb.GetSize());
}

size_t parse_header(const uint8_t* buf, size_t len, HeaderResult& out) {
    // Need at least the 4-byte size prefix to know how long the body is.
    if (len < 4) return 0;
    uint32_t body = flatbuffers::GetPrefixedSize(buf);
    size_t consumed = 4 + static_cast<size_t>(body);
    // Guard against a truncated/short buffer.
    if (consumed > len) return 0;

    // Get a typed view over the header buffer (no copy).
    const Header* h = flatbuffers::GetSizePrefixedRoot<Header>(buf);
    if (h == nullptr) return 0;

    // Copy the scalar/string metadata out into the plain result struct.
    if (h->name()) out.name = h->name()->str();
    out.geometry_type = static_cast<uint8_t>(h->geometry_type());
    out.features_count = h->features_count();
    out.index_node_size = h->index_node_size();

    // Pull the attribute column names and types (aligned by index).
    if (h->columns()) {
        const auto* cols = h->columns();
        out.col_names.reserve(cols->size());
        out.col_types.reserve(cols->size());
        for (uint32_t i = 0; i < cols->size(); ++i) {
            const Column* c = cols->Get(i);
            out.col_names.push_back(c->name() ? c->name()->str()
                                              : std::string());
            out.col_types.push_back(static_cast<uint8_t>(c->type()));
        }
    }
    // Pull the CRS info (WKT string and/or authority org:code).
    if (h->crs()) {
        const Crs* c = h->crs();
        if (c->wkt()) out.crs_wkt = c->wkt()->str();
        if (c->org()) out.crs_org = c->org()->str();
        out.crs_code = c->code();
    }
    // Pull the layer envelope when present (minx, miny, maxx, maxy).
    if (h->envelope() && h->envelope()->size() >= 4) {
        out.has_envelope = 1;
        out.env_minx = h->envelope()->Get(0);
        out.env_miny = h->envelope()->Get(1);
        out.env_maxx = h->envelope()->Get(2);
        out.env_maxy = h->envelope()->Get(3);
    }
    // Report how many bytes the header occupied so the caller can advance.
    return consumed;
}

// --- Geometry helpers -----------------------------------------------------
// Compute the bounding box of the collected coordinates and flag emptiness.
static void expand_env(GeometryResult& g) {
    g.empty = g.xy.empty() ? 1 : 0;
    if (g.xy.empty()) return;
    // Seed the min/max with the first coordinate pair, then fold in the rest.
    double minx = g.xy[0], miny = g.xy[1], maxx = g.xy[0], maxy = g.xy[1];
    for (size_t i = 0; i + 1 < g.xy.size(); i += 2) {
        double x = g.xy[i], y = g.xy[i + 1];
        if (x < minx) minx = x;
        if (x > maxx) maxx = x;
        if (y < miny) miny = y;
        if (y > maxy) maxy = y;
    }
    g.minx = minx;
    g.miny = miny;
    g.maxx = maxx;
    g.maxy = maxy;
}

// Append a simple (non-part) Geometry's coords/ends into the flat result.
static void collect_simple(const Geometry* geo, GeometryResult& out) {
    // Where this component's coordinate pairs begin within the global xy array.
    uint32_t base_pairs = static_cast<uint32_t>(out.xy.size() / 2);
    // Copy the interleaved x, y coordinates.
    const auto* xy = geo->xy();
    if (xy) {
        out.xy.reserve(out.xy.size() + xy->size());
        for (uint32_t i = 0; i < xy->size(); ++i) out.xy.push_back(xy->Get(i));
    }
    // Copy the ring ends, shifting them by the component's base offset so they
    // stay global (cumulative over all previously collected components).
    const auto* ends = geo->ends();
    if (ends && ends->size() > 0) {
        out.ends.reserve(out.ends.size() + ends->size());
        for (uint32_t i = 0; i < ends->size(); ++i)
            out.ends.push_back(base_pairs + ends->Get(i));
    } else if (xy) {
        // Single ring/line with no explicit ends -> one end at the tail.
        out.ends.push_back(static_cast<uint32_t>(out.xy.size() / 2));
    }
}

// Flatten a (possibly multi-part) Geometry into xy/ends/parts.
static void collect_geometry(const Geometry* geo, GeometryResult& out) {
    const auto* parts = geo->parts();
    if (parts && parts->size() > 0) {
        // MultiPolygon: each part is itself a polygon; record a part boundary
        // (as a cumulative ring count) after collecting each one.
        for (uint32_t p = 0; p < parts->size(); ++p) {
            collect_simple(parts->Get(p), out);
            out.parts.push_back(static_cast<uint32_t>(out.ends.size()));
        }
    } else {
        // Simple geometry (point/line/polygon): a single component, no parts.
        collect_simple(geo, out);
    }
}

// --- Feature --------------------------------------------------------------
// Build one Polygon sub-geometry from a slice of the flat xy/ends arrays.
static flatbuffers::Offset<Geometry> build_polygon(
    flatbuffers::FlatBufferBuilder& fbb, const double* xy_ptr,
    size_t pair_start, size_t pair_end, const std::vector<uint32_t>& ends,
    size_t end_start, size_t end_end, uint8_t geom_type) {
    // Copy this polygon's coordinate pairs into a local, zero-based array.
    // ``xy_ptr`` is contiguous interleaved x, y, so the slice copies directly.
    std::vector<double> xy(xy_ptr + 2 * pair_start, xy_ptr + 2 * pair_end);
    // Re-base the ring ends so they are relative to this polygon's first pair.
    std::vector<uint32_t> local_ends;
    if (end_end > end_start) {
        local_ends.reserve(end_end - end_start);
        for (size_t e = end_start; e < end_end; ++e)
            local_ends.push_back(ends[e] - static_cast<uint32_t>(pair_start));
    }
    const std::vector<uint32_t>* ends_arg =
        local_ends.empty() ? nullptr : &local_ends;
    return CreateGeometryDirect(fbb, ends_arg, &xy, nullptr, nullptr, nullptr,
                                nullptr, static_cast<GeometryType>(geom_type),
                                nullptr);
}

std::string build_feature(uint8_t geom_type, const std::vector<double>& xy,
                          const std::vector<uint32_t>& ends,
                          const std::vector<uint32_t>& parts,
                          const std::vector<uint8_t>& props) {
    flatbuffers::FlatBufferBuilder fbb;

    flatbuffers::Offset<Geometry> geom_off;
    if (geom_type == static_cast<uint8_t>(GeometryType::MultiPolygon) &&
        !parts.empty()) {
        // MultiPolygon: emit each polygon as a child geometry under `parts`.
        std::vector<flatbuffers::Offset<Geometry>> part_offsets;
        part_offsets.reserve(parts.size());
        size_t end_start = 0, pair_start = 0;
        for (size_t p = 0; p < parts.size(); ++p) {
            // `parts[p]` is the cumulative ring count at the end of polygon p;
            // the last ring's end gives the pair boundary of this polygon.
            size_t end_end = parts[p];
            size_t pair_end =
                ends.empty() ? (xy.size() / 2) : ends[end_end - 1];
            part_offsets.push_back(build_polygon(
                fbb, xy.data(), pair_start, pair_end, ends, end_start, end_end,
                static_cast<uint8_t>(GeometryType::Polygon)));
            // Advance the ring/pair cursors to the next polygon.
            end_start = end_end;
            pair_start = pair_end;
        }
        auto parts_vec = fbb.CreateVector(part_offsets);
        GeometryBuilder gb(fbb);
        gb.add_type(static_cast<GeometryType>(geom_type));
        gb.add_parts(parts_vec);
        geom_off = gb.Finish();
    } else {
        // Simple geometry: a single flat coordinate array with optional ends.
        const std::vector<uint32_t>* ends_arg = ends.empty() ? nullptr : &ends;
        geom_off = CreateGeometryDirect(
            fbb, ends_arg, &xy, nullptr, nullptr, nullptr, nullptr,
            static_cast<GeometryType>(geom_type), nullptr);
    }

    // The attribute values are an opaque, pre-encoded property blob.
    flatbuffers::Offset<flatbuffers::Vector<uint8_t>> props_off = 0;
    if (!props.empty()) props_off = fbb.CreateVector(props);

    // Assemble the Feature table (geometry + properties).
    FeatureBuilder fb(fbb);
    fb.add_geometry(geom_off);
    if (props_off.o != 0) fb.add_properties(props_off);
    auto feat = fb.Finish();
    // Size-prefixed so features can be streamed/concatenated back to back.
    fbb.FinishSizePrefixed(feat);

    return std::string(reinterpret_cast<const char*>(fbb.GetBufferPointer()),
                       fbb.GetSize());
}

size_t parse_feature(const uint8_t* buf, size_t len, GeometryResult& geom,
                     std::string& out_props) {
    // Read the size prefix and bounds-check as in parse_header.
    if (len < 4) return 0;
    uint32_t body = flatbuffers::GetPrefixedSize(buf);
    size_t consumed = 4 + static_cast<size_t>(body);
    if (consumed > len) return 0;

    const Feature* f = flatbuffers::GetSizePrefixedRoot<Feature>(buf);
    if (f == nullptr) return 0;

    // Flatten the geometry and compute its bounding box.
    const Geometry* g = f->geometry();
    if (g) {
        geom.geometry_type = static_cast<uint8_t>(g->type());
        collect_geometry(g, geom);
        expand_env(geom);
    }
    // Copy the raw property blob out for the Python layer to decode.
    const auto* props = f->properties();
    if (props && props->size() > 0) {
        out_props.assign(reinterpret_cast<const char*>(props->Data()),
                         props->size());
    }
    // Report the byte length so the reader can advance to the next feature.
    return consumed;
}

// --- Packed Hilbert R-tree ------------------------------------------------
// Return feature indices sorted by Hilbert curve value and fill the overall
// extent. Ordering features along the Hilbert curve makes the packed R-tree
// spatially coherent (nearby features end up near each other in the file).
std::vector<uint64_t> hilbert_order(const std::vector<double>& env,
                                    double extent[4]) {
    // `env` is 4 doubles per feature: minx, miny, maxx, maxy.
    size_t n = env.size() / 4;
    std::vector<uint64_t> order(n);
    std::iota(order.begin(), order.end(), 0);
    if (n == 0) {
        extent[0] = extent[1] = extent[2] = extent[3] = 0;
        return order;
    }

    // First pass: accumulate the total extent over all feature envelopes.
    NodeItem ext = NodeItem::create(0);
    for (size_t i = 0; i < n; ++i) {
        NodeItem ni{env[4 * i], env[4 * i + 1], env[4 * i + 2], env[4 * i + 3],
                    0};
        ext.expand(ni);
    }
    extent[0] = ext.minX;
    extent[1] = ext.minY;
    extent[2] = ext.maxX;
    extent[3] = ext.maxY;

    // Second pass: map each envelope's centre to a Hilbert value within the
    // total extent (the vendored `hilbert` helper does the bit interleaving).
    const double width = ext.width();
    const double height = ext.height();
    std::vector<uint32_t> h(n);
    for (size_t i = 0; i < n; ++i) {
        NodeItem ni{env[4 * i], env[4 * i + 1], env[4 * i + 2], env[4 * i + 3],
                    0};
        h[i] = hilbert(ni, HILBERT_MAX, ext.minX, ext.minY, width, height);
    }
    // Sort indices by descending Hilbert value (matches the FlatGeobuf writer).
    std::sort(order.begin(), order.end(),
              [&h](uint64_t a, uint64_t b) { return h[a] > h[b]; });
    return order;
}

// Build the serialized packed R-tree bytes from Hilbert-ordered envelopes and
// their (final) byte offsets within the feature section.
std::string build_index(const std::vector<double>& env_ordered,
                        const std::vector<uint64_t>& offsets,
                        const double extent[4], uint16_t node_size) {
    size_t n = env_ordered.size() / 4;
    // Turn the flat envelope array into NodeItems carrying the feature offset.
    std::vector<NodeItem> nodes;
    nodes.reserve(n);
    for (size_t i = 0; i < n; ++i) {
        nodes.push_back(NodeItem{env_ordered[4 * i], env_ordered[4 * i + 1],
                                 env_ordered[4 * i + 2], env_ordered[4 * i + 3],
                                 offsets[i]});
    }
    NodeItem ext{extent[0], extent[1], extent[2], extent[3], 0};
    // The vendored PackedRTree builds the node hierarchy from the leaf items.
    PackedRTree tree(nodes, ext, node_size);
    // Stream the tree into a string buffer (this is what gets written to file).
    std::string out;
    tree.streamWrite([&out](uint8_t* data, size_t size) {
        out.append(reinterpret_cast<const char*>(data), size);
    });
    return out;
}

// Query the packed R-tree for features whose envelope intersects the bbox;
// returns their byte offsets within the feature section.
std::vector<uint64_t> search_index(const uint8_t* data, size_t data_len,
                                   uint64_t num_items, uint16_t node_size,
                                   double minx, double miny, double maxx,
                                   double maxy) {
    (void)data_len;  // Length is implied by num_items/node_size.
    // Reconstruct the tree in place over the serialized bytes and search it.
    PackedRTree tree(data, num_items, node_size);
    auto hits = tree.search(minx, miny, maxx, maxy);
    // Extract just the feature offsets from the hit records.
    std::vector<uint64_t> offsets;
    offsets.reserve(hits.size());
    for (const auto& h : hits) offsets.push_back(h.offset);
    // Sort so callers read features in file order (better sequential I/O).
    std::sort(offsets.begin(), offsets.end());
    return offsets;
}

// Serialized byte size of the index for a given feature count / node size.
// Used to skip the index section when scanning, without parsing it.
uint64_t index_size(uint64_t num_items, uint16_t node_size) {
    if (num_items == 0) return 0;
    return PackedRTree::size(num_items, node_size);
}

}  // namespace fiatfgb
