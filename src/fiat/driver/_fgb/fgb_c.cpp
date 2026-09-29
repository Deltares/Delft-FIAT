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
    flatbuffers::FlatBufferBuilder fbb;

    std::vector<flatbuffers::Offset<Column>> cols;
    cols.reserve(col_names.size());
    for (size_t i = 0; i < col_names.size(); ++i) {
        cols.push_back(CreateColumnDirect(
            fbb, col_names[i].c_str(), static_cast<ColumnType>(col_types[i])));
    }
    auto cols_off = fbb.CreateVector(cols);

    flatbuffers::Offset<Crs> crs_off = 0;
    if (!crs_wkt.empty() || !crs_org.empty() || crs_code != 0) {
        crs_off = CreateCrsDirect(
            fbb, crs_org.empty() ? nullptr : crs_org.c_str(), crs_code, nullptr,
            nullptr, crs_wkt.empty() ? nullptr : crs_wkt.c_str(), nullptr);
    }

    flatbuffers::Offset<flatbuffers::Vector<double>> env_off = 0;
    if (has_envelope) {
        std::vector<double> env = {minx, miny, maxx, maxy};
        env_off = fbb.CreateVector(env);
    }

    auto name_off = fbb.CreateString(name);

    HeaderBuilder hb(fbb);
    hb.add_name(name_off);
    if (has_envelope) hb.add_envelope(env_off);
    hb.add_geometry_type(static_cast<GeometryType>(geometry_type));
    hb.add_columns(cols_off);
    hb.add_features_count(features_count);
    hb.add_index_node_size(index_node_size);
    if (crs_off.o != 0) hb.add_crs(crs_off);
    auto header = hb.Finish();
    fbb.FinishSizePrefixed(header);

    return std::string(reinterpret_cast<const char*>(fbb.GetBufferPointer()),
                       fbb.GetSize());
}

size_t parse_header(const uint8_t* buf, size_t len, HeaderResult& out) {
    if (len < 4) return 0;
    uint32_t body = flatbuffers::GetPrefixedSize(buf);
    size_t consumed = 4 + static_cast<size_t>(body);
    if (consumed > len) return 0;

    const Header* h = flatbuffers::GetSizePrefixedRoot<Header>(buf);
    if (h == nullptr) return 0;

    if (h->name()) out.name = h->name()->str();
    out.geometry_type = static_cast<uint8_t>(h->geometry_type());
    out.features_count = h->features_count();
    out.index_node_size = h->index_node_size();

    if (h->columns()) {
        const auto* cols = h->columns();
        for (uint32_t i = 0; i < cols->size(); ++i) {
            const Column* c = cols->Get(i);
            out.col_names.push_back(c->name() ? c->name()->str()
                                              : std::string());
            out.col_types.push_back(static_cast<uint8_t>(c->type()));
        }
    }
    if (h->crs()) {
        const Crs* c = h->crs();
        if (c->wkt()) out.crs_wkt = c->wkt()->str();
        if (c->org()) out.crs_org = c->org()->str();
        out.crs_code = c->code();
    }
    if (h->envelope() && h->envelope()->size() >= 4) {
        out.has_envelope = 1;
        out.env_minx = h->envelope()->Get(0);
        out.env_miny = h->envelope()->Get(1);
        out.env_maxx = h->envelope()->Get(2);
        out.env_maxy = h->envelope()->Get(3);
    }
    return consumed;
}

// --- Geometry helpers -----------------------------------------------------
static void expand_env(GeometryResult& g) {
    g.empty = g.xy.empty() ? 1 : 0;
    if (g.xy.empty()) return;
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
    uint32_t base_pairs = static_cast<uint32_t>(out.xy.size() / 2);
    const auto* xy = geo->xy();
    if (xy) {
        for (uint32_t i = 0; i < xy->size(); ++i) out.xy.push_back(xy->Get(i));
    }
    const auto* ends = geo->ends();
    if (ends && ends->size() > 0) {
        for (uint32_t i = 0; i < ends->size(); ++i)
            out.ends.push_back(base_pairs + ends->Get(i));
    } else if (xy) {
        // Single ring/line with no explicit ends -> one end at the tail.
        out.ends.push_back(static_cast<uint32_t>(out.xy.size() / 2));
    }
}

static void collect_geometry(const Geometry* geo, GeometryResult& out) {
    const auto* parts = geo->parts();
    if (parts && parts->size() > 0) {
        for (uint32_t p = 0; p < parts->size(); ++p) {
            collect_simple(parts->Get(p), out);
            out.parts.push_back(static_cast<uint32_t>(out.ends.size()));
        }
    } else {
        collect_simple(geo, out);
    }
}

// --- Feature --------------------------------------------------------------
static flatbuffers::Offset<Geometry> build_polygon(
    flatbuffers::FlatBufferBuilder& fbb, const double* xy_ptr,
    size_t pair_start, size_t pair_end, const std::vector<uint32_t>& ends,
    size_t end_start, size_t end_end, uint8_t geom_type) {
    std::vector<double> xy;
    for (size_t p = pair_start; p < pair_end; ++p) {
        xy.push_back(xy_ptr[2 * p]);
        xy.push_back(xy_ptr[2 * p + 1]);
    }
    std::vector<uint32_t> local_ends;
    if (end_end > end_start) {
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
        std::vector<flatbuffers::Offset<Geometry>> part_offsets;
        size_t end_start = 0, pair_start = 0;
        for (size_t p = 0; p < parts.size(); ++p) {
            size_t end_end = parts[p];
            size_t pair_end =
                ends.empty() ? (xy.size() / 2) : ends[end_end - 1];
            part_offsets.push_back(build_polygon(
                fbb, xy.data(), pair_start, pair_end, ends, end_start, end_end,
                static_cast<uint8_t>(GeometryType::Polygon)));
            end_start = end_end;
            pair_start = pair_end;
        }
        auto parts_vec = fbb.CreateVector(part_offsets);
        GeometryBuilder gb(fbb);
        gb.add_type(static_cast<GeometryType>(geom_type));
        gb.add_parts(parts_vec);
        geom_off = gb.Finish();
    } else {
        const std::vector<uint32_t>* ends_arg = ends.empty() ? nullptr : &ends;
        geom_off = CreateGeometryDirect(
            fbb, ends_arg, &xy, nullptr, nullptr, nullptr, nullptr,
            static_cast<GeometryType>(geom_type), nullptr);
    }

    flatbuffers::Offset<flatbuffers::Vector<uint8_t>> props_off = 0;
    if (!props.empty()) props_off = fbb.CreateVector(props);

    FeatureBuilder fb(fbb);
    fb.add_geometry(geom_off);
    if (props_off.o != 0) fb.add_properties(props_off);
    auto feat = fb.Finish();
    fbb.FinishSizePrefixed(feat);

    return std::string(reinterpret_cast<const char*>(fbb.GetBufferPointer()),
                       fbb.GetSize());
}

size_t parse_feature(const uint8_t* buf, size_t len, GeometryResult& geom,
                     std::string& out_props) {
    if (len < 4) return 0;
    uint32_t body = flatbuffers::GetPrefixedSize(buf);
    size_t consumed = 4 + static_cast<size_t>(body);
    if (consumed > len) return 0;

    const Feature* f = flatbuffers::GetSizePrefixedRoot<Feature>(buf);
    if (f == nullptr) return 0;

    const Geometry* g = f->geometry();
    if (g) {
        geom.geometry_type = static_cast<uint8_t>(g->type());
        collect_geometry(g, geom);
        expand_env(geom);
    }
    const auto* props = f->properties();
    if (props && props->size() > 0) {
        out_props.assign(reinterpret_cast<const char*>(props->Data()),
                         props->size());
    }
    return consumed;
}

// --- Packed Hilbert R-tree ------------------------------------------------
std::vector<uint64_t> hilbert_order(const std::vector<double>& env,
                                    double extent[4]) {
    size_t n = env.size() / 4;
    std::vector<uint64_t> order(n);
    std::iota(order.begin(), order.end(), 0);
    if (n == 0) {
        extent[0] = extent[1] = extent[2] = extent[3] = 0;
        return order;
    }

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

    const double width = ext.width();
    const double height = ext.height();
    std::vector<uint32_t> h(n);
    for (size_t i = 0; i < n; ++i) {
        NodeItem ni{env[4 * i], env[4 * i + 1], env[4 * i + 2], env[4 * i + 3],
                    0};
        h[i] = hilbert(ni, HILBERT_MAX, ext.minX, ext.minY, width, height);
    }
    std::sort(order.begin(), order.end(),
              [&h](uint64_t a, uint64_t b) { return h[a] > h[b]; });
    return order;
}

std::string build_index(const std::vector<double>& env_ordered,
                        const std::vector<uint64_t>& offsets,
                        const double extent[4], uint16_t node_size) {
    size_t n = env_ordered.size() / 4;
    std::vector<NodeItem> nodes;
    nodes.reserve(n);
    for (size_t i = 0; i < n; ++i) {
        nodes.push_back(NodeItem{env_ordered[4 * i], env_ordered[4 * i + 1],
                                 env_ordered[4 * i + 2], env_ordered[4 * i + 3],
                                 offsets[i]});
    }
    NodeItem ext{extent[0], extent[1], extent[2], extent[3], 0};
    PackedRTree tree(nodes, ext, node_size);
    std::string out;
    tree.streamWrite([&out](uint8_t* data, size_t size) {
        out.append(reinterpret_cast<const char*>(data), size);
    });
    return out;
}

std::vector<uint64_t> search_index(const uint8_t* data, size_t data_len,
                                   uint64_t num_items, uint16_t node_size,
                                   double minx, double miny, double maxx,
                                   double maxy) {
    (void)data_len;
    PackedRTree tree(data, num_items, node_size);
    auto hits = tree.search(minx, miny, maxx, maxy);
    std::vector<uint64_t> offsets;
    offsets.reserve(hits.size());
    for (const auto& h : hits) offsets.push_back(h.offset);
    std::sort(offsets.begin(), offsets.end());
    return offsets;
}

uint64_t index_size(uint64_t num_items, uint16_t node_size) {
    if (num_items == 0) return 0;
    return PackedRTree::size(num_items, node_size);
}

}  // namespace fiatfgb
