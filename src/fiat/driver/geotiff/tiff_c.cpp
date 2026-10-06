/* Implementation of the hand-rolled TIFF / GeoTIFF / COG codec.
 * See tiff_c.h for the specifications followed. All multi-byte output is
 * written little-endian ("II"); the parser handles both byte orders.
 *
 * Scope: classic TIFF (32-bit offsets). BigTIFF is detected and rejected by the
 * parser (returns 0); the writer only emits classic TIFF. This matches the
 * driver's documented v1 scope (outputs below 4 GiB).
 */
#include "tiff_c.h"

#include <zlib.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>

namespace fiatgtiff {

namespace {

// --- Endian-aware little helpers for reading ------------------------------
inline uint16_t rd_u16(const uint8_t* p, bool be) {
    return be ? (uint16_t)((p[0] << 8) | p[1]) : (uint16_t)((p[1] << 8) | p[0]);
}
inline uint32_t rd_u32(const uint8_t* p, bool be) {
    if (be)
        return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
               ((uint32_t)p[2] << 8) | (uint32_t)p[3];
    return ((uint32_t)p[3] << 24) | ((uint32_t)p[2] << 16) |
           ((uint32_t)p[1] << 8) | (uint32_t)p[0];
}
inline double rd_f64(const uint8_t* p, bool be) {
    uint8_t b[8];
    for (int i = 0; i < 8; ++i) b[i] = be ? p[7 - i] : p[i];
    double d;
    std::memcpy(&d, b, 8);
    return d;
}

// Byte size of a TIFF field type (tag 6.0 types 1..12). 0 for unknown.
int type_size(uint16_t t) {
    switch (t) {
        case 1:
        case 2:
        case 6:
        case 7:
            return 1;  // BYTE/ASCII/SBYTE/UNDEFINED
        case 3:
        case 8:
            return 2;  // SHORT/SSHORT
        case 4:
        case 9:
        case 11:
            return 4;  // LONG/SLONG/FLOAT
        case 5:
        case 10:
        case 12:
            return 8;  // RATIONAL/SRATIONAL/DOUBLE
        default:
            return 0;
    }
}

struct Entry {
    uint16_t tag = 0;
    uint16_t type = 0;
    uint32_t count = 0;
    const uint8_t* valptr = nullptr;  // points to value (inline or external)
};

// Pull one integer-ish field value (index idx) as uint64.
uint64_t entry_u64(const Entry& e, const uint8_t* base, size_t len, bool be,
                   uint32_t idx) {
    int ts = type_size(e.type);
    const uint8_t* p = e.valptr + (size_t)idx * ts;
    if (p + ts > base + len) return 0;
    switch (e.type) {
        case 3:
        case 8:
            return rd_u16(p, be);
        case 4:
        case 9:
            return rd_u32(p, be);
        case 1:
        case 2:
        case 6:
        case 7:
            return *p;
        default:
            return 0;
    }
}

double entry_f64(const Entry& e, const uint8_t* base, size_t len, bool be,
                 uint32_t idx) {
    int ts = type_size(e.type);
    const uint8_t* p = e.valptr + (size_t)idx * ts;
    if (p + ts > base + len) return 0;
    if (e.type == 12) return rd_f64(p, be);
    if (e.type == 11) {  // FLOAT
        uint8_t b[4];
        for (int i = 0; i < 4; ++i) b[i] = be ? p[3 - i] : p[i];
        float f;
        std::memcpy(&f, b, 4);
        return f;
    }
    if (e.type == 5) {  // RATIONAL
        uint32_t n = rd_u32(p, be), d = rd_u32(p + 4, be);
        return d ? (double)n / d : 0.0;
    }
    return (double)entry_u64(e, base, len, be, idx);
}

std::string entry_ascii(const Entry& e, const uint8_t* base, size_t len) {
    const uint8_t* p = e.valptr;
    if (p + e.count > base + len) return std::string();
    size_t n = e.count;
    while (n > 0 && p[n - 1] == '\0') --n;  // strip trailing NULs
    return std::string(reinterpret_cast<const char*>(p), n);
}

// Minimal extraction of <Item name="..." sample="...">value</Item> entries from
// a GDAL_METADATA XML blob (tag 42112). Not a full XML parser; adequate for the
// flat metadata GDAL and this driver emit.
void parse_gdal_metadata(const std::string& xml, std::vector<MetaItem>& out) {
    size_t pos = 0;
    while (true) {
        size_t s = xml.find("<Item", pos);
        if (s == std::string::npos) break;
        size_t gt = xml.find('>', s);
        if (gt == std::string::npos) break;
        std::string attrs = xml.substr(s + 5, gt - (s + 5));
        size_t e = xml.find("</Item>", gt);
        if (e == std::string::npos) break;
        std::string value = xml.substr(gt + 1, e - (gt + 1));
        MetaItem item;
        item.value = value;
        size_t np = attrs.find("name=\"");
        if (np != std::string::npos) {
            size_t ne = attrs.find('"', np + 6);
            item.name = attrs.substr(np + 6, ne - (np + 6));
        }
        size_t sp = attrs.find("sample=\"");
        if (sp != std::string::npos) {
            size_t se = attrs.find('"', sp + 8);
            item.sample =
                std::atoi(attrs.substr(sp + 8, se - (sp + 8)).c_str());
        }
        out.push_back(item);
        pos = e + 7;
    }
}

}  // namespace

int parse_tiff(const uint8_t* buf, size_t len, TiffInfo& out) {
    if (!buf || len < 8) return 0;
    bool be;
    if (buf[0] == 'I' && buf[1] == 'I')
        be = false;
    else if (buf[0] == 'M' && buf[1] == 'M')
        be = true;
    else
        return 0;
    out.big_endian = be ? 1 : 0;
    uint16_t magic = rd_u16(buf + 2, be);
    if (magic == 43) {  // BigTIFF -> unsupported in v1
        out.is_bigtiff = 1;
        return 0;
    }
    if (magic != 42) return 0;

    uint32_t ifd_off = rd_u32(buf + 4, be);
    bool first_ifd = true;
    int guard = 0;
    while (ifd_off != 0 && guard++ < 1024) {
        if (ifd_off + 2 > len) return 0;
        uint16_t n = rd_u16(buf + ifd_off, be);
        size_t entries_at = ifd_off + 2;
        if (entries_at + (size_t)n * 12 + 4 > len) return 0;

        std::map<uint16_t, Entry> tags;
        for (uint16_t i = 0; i < n; ++i) {
            const uint8_t* ep = buf + entries_at + (size_t)i * 12;
            Entry e;
            e.tag = rd_u16(ep, be);
            e.type = rd_u16(ep + 2, be);
            e.count = rd_u32(ep + 4, be);
            int ts = type_size(e.type);
            size_t total = (size_t)e.count * ts;
            if (total <= 4) {
                e.valptr = ep + 8;  // inline
            } else {
                uint32_t voff = rd_u32(ep + 8, be);
                if (voff + total > len) return 0;
                e.valptr = buf + voff;
            }
            tags[e.tag] = e;
        }

        IfdInfo ifd;
        auto get1 = [&](uint16_t tag, uint64_t def) -> uint64_t {
            auto it = tags.find(tag);
            return it == tags.end() ? def
                                    : entry_u64(it->second, buf, len, be, 0);
        };
        ifd.width = (uint32_t)get1(256, 0);
        ifd.height = (uint32_t)get1(257, 0);
        ifd.bits_per_sample = (uint16_t)get1(258, 1);
        ifd.compression = (uint16_t)get1(259, 1);
        ifd.samples_per_pixel = (uint16_t)get1(277, 1);
        ifd.rows_per_strip = (uint32_t)get1(278, 0);
        ifd.planar_config = (uint16_t)get1(284, 1);
        ifd.predictor = (uint16_t)get1(317, 1);
        ifd.tile_width = (uint32_t)get1(322, 0);
        ifd.tile_height = (uint32_t)get1(323, 0);
        ifd.sample_format = (uint16_t)get1(339, 1);
        ifd.is_reduced = (get1(254, 0) & 0x1) ? 1 : 0;

        // Tile vs strip offsets / counts.
        auto fill_u64 = [&](uint16_t tag, std::vector<uint64_t>& dst) {
            auto it = tags.find(tag);
            if (it == tags.end()) return;
            for (uint32_t k = 0; k < it->second.count; ++k)
                dst.push_back(entry_u64(it->second, buf, len, be, k));
        };
        if (ifd.tile_width > 0 && tags.count(324)) {
            ifd.is_tiled = 1;
            fill_u64(324, ifd.tile_offsets);
            fill_u64(325, ifd.tile_bytecounts);
        } else {
            ifd.is_tiled = 0;
            fill_u64(273, ifd.tile_offsets);
            fill_u64(279, ifd.tile_bytecounts);
        }

        // Georeferencing + GDAL tags are taken from the first IFD only.
        if (first_ifd) {
            auto it = tags.find(33550);
            if (it != tags.end()) {
                out.has_pixel_scale = 1;
                for (uint32_t k = 0; k < 3 && k < it->second.count; ++k)
                    out.pixel_scale[k] = entry_f64(it->second, buf, len, be, k);
            }
            it = tags.find(33922);
            if (it != tags.end()) {
                out.has_tiepoint = 1;
                for (uint32_t k = 0; k < 6 && k < it->second.count; ++k)
                    out.tiepoint[k] = entry_f64(it->second, buf, len, be, k);
            }
            // GeoKeyDirectory (34735) + GeoAsciiParams (34737).
            std::string ascii;
            auto ait = tags.find(34737);
            if (ait != tags.end()) ascii = entry_ascii(ait->second, buf, len);
            auto git = tags.find(34735);
            if (git != tags.end()) {
                const Entry& g = git->second;
                if (g.count >= 4) {
                    uint32_t nkeys = (uint32_t)entry_u64(g, buf, len, be, 3);
                    for (uint32_t k = 0; k < nkeys; ++k) {
                        uint32_t base = 4 + k * 4;
                        if (base + 4 > g.count) break;
                        uint16_t kid =
                            (uint16_t)entry_u64(g, buf, len, be, base);
                        uint16_t loc =
                            (uint16_t)entry_u64(g, buf, len, be, base + 1);
                        uint16_t cnt =
                            (uint16_t)entry_u64(g, buf, len, be, base + 2);
                        uint16_t val =
                            (uint16_t)entry_u64(g, buf, len, be, base + 3);
                        if (kid == 1024)
                            out.model_type = val;
                        else if (kid == 1025)
                            out.raster_type = val;
                        else if (kid == 2048 || kid == 3072) {
                            if (val != 0 && val != 32767) out.epsg = val;
                        } else if ((kid == 1026 || kid == 3073) &&
                                   loc == 34737) {
                            if ((size_t)val + cnt <= ascii.size() + 1) {
                                size_t c = cnt;
                                if (c > 0 && (val + c - 1) <= ascii.size() &&
                                    ascii[val + c - 1] == '|')
                                    c -= 1;  // drop '|' delimiter
                                if (val < ascii.size())
                                    out.crs_citation = ascii.substr(val, c);
                            }
                        }
                    }
                }
            }
            auto nit = tags.find(42113);
            if (nit != tags.end()) {
                std::string s = entry_ascii(nit->second, buf, len);
                if (!s.empty()) {
                    out.has_nodata = 1;
                    out.nodata = std::atof(s.c_str());
                }
            }
            auto mit = tags.find(42112);
            if (mit != tags.end())
                parse_gdal_metadata(entry_ascii(mit->second, buf, len),
                                    out.meta_items);
        }

        out.ifds.push_back(std::move(ifd));
        first_ifd = false;
        ifd_off = rd_u32(buf + entries_at + (size_t)n * 12, be);
    }
    return out.ifds.empty() ? 0 : 1;
}

std::string deflate_block(const uint8_t* data, size_t len, int level) {
    uLongf bound = compressBound((uLong)len);
    std::string out;
    out.resize(bound);
    uLongf dlen = bound;
    int rc = compress2(reinterpret_cast<Bytef*>(&out[0]), &dlen,
                       reinterpret_cast<const Bytef*>(data), (uLong)len, level);
    if (rc != Z_OK) return std::string();
    out.resize(dlen);
    return out;
}

size_t inflate_block(const uint8_t* src, size_t src_len, uint8_t* dst,
                     size_t dst_cap) {
    uLongf dlen = (uLongf)dst_cap;
    int rc = uncompress(reinterpret_cast<Bytef*>(dst), &dlen,
                        reinterpret_cast<const Bytef*>(src), (uLong)src_len);
    if (rc != Z_OK) return 0;
    return (size_t)dlen;
}

// --- COG writer helpers ---------------------------------------------------
namespace {

// Little-endian serializers used when emitting the header.
void put_u16(std::string& s, uint16_t v) {
    s.push_back((char)(v & 0xff));
    s.push_back((char)((v >> 8) & 0xff));
}
void put_u32(std::string& s, uint32_t v) {
    s.push_back((char)(v & 0xff));
    s.push_back((char)((v >> 8) & 0xff));
    s.push_back((char)((v >> 16) & 0xff));
    s.push_back((char)((v >> 24) & 0xff));
}
void put_f64(std::string& s, double v) {
    uint8_t b[8];
    std::memcpy(b, &v, 8);
    s.append(reinterpret_cast<char*>(b), 8);
}

// A field whose value bytes are already serialized little-endian. If the bytes
// fit in 4 their are stored inline, otherwise in the external pool.
struct Field {
    uint16_t tag = 0;
    uint16_t type = 0;
    uint32_t count = 0;
    std::string bytes;  // serialized values (little-endian)
};

std::string ser_shorts(const std::vector<uint16_t>& v) {
    std::string s;
    for (uint16_t x : v) put_u16(s, x);
    return s;
}
std::string ser_longs(const std::vector<uint32_t>& v) {
    std::string s;
    for (uint32_t x : v) put_u32(s, x);
    return s;
}
std::string ser_doubles(const std::vector<double>& v) {
    std::string s;
    for (double x : v) put_f64(s, x);
    return s;
}

// Round a byte offset up to the next even address (TIFF word alignment).
inline uint64_t align2(uint64_t v) { return (v + 1) & ~uint64_t(1); }

// Format a nodata value exactly as GDAL writes the GDAL_NODATA tag (42113):
// a plain "%.18g" numeric ASCII string. Formatting here (rather than on the
// Python side) avoids language-specific reprs such as NumPy's
// "np.float32(-9999.0)", which GDAL / QGIS cannot parse (so the nodata would be
// silently ignored).
std::string format_gdal_nodata(double v) {
    char buf[64];
    std::snprintf(buf, sizeof(buf), "%.18g", v);
    return std::string(buf);
}

// Assemble the GDAL_METADATA (tag 42112) XML from per-band items. A DESCRIPTION
// item carries role="description" (the GDAL convention for a band's name); all
// other items are plain per-band key/value pairs.
std::string build_gdal_metadata_xml(const std::vector<MetaItem>& items) {
    if (items.empty()) return std::string();
    std::string xml = "<GDALMetadata>";
    for (const auto& it : items) {
        xml += "<Item name=\"";
        xml += it.name;
        xml += "\" sample=\"";
        xml += std::to_string(it.sample);
        xml += "\"";
        if (it.name == "DESCRIPTION") xml += " role=\"description\"";
        xml += ">";
        xml += it.value;
        xml += "</Item>";
    }
    xml += "</GDALMetadata>";
    return xml;
}

// Build the GeoKeyDirectory payload (tag 34735) and fill the GeoAsciiParams
// pool (tag 34737) for `spec`. GDAL stores these on the full-resolution IFD
// only. Keys are emitted in ascending KeyID order (GeoTIFF 1.1 requirement).
std::vector<uint16_t> make_geokeys(const CogSpec& spec,
                                   std::string& ascii_pool) {
    struct GK {
        uint16_t id, loc, cnt, val;
    };
    std::vector<GK> gks;
    gks.push_back({1024, 0, 1, (uint16_t)spec.model_type});
    gks.push_back({1025, 0, 1, (uint16_t)spec.raster_type});
    auto add_citation = [&](uint16_t keyid, const std::string& text) {
        uint16_t off = (uint16_t)ascii_pool.size();
        ascii_pool += text;
        ascii_pool += '|';
        gks.push_back({keyid, 34737, (uint16_t)(text.size() + 1), off});
    };
    if (spec.model_type == 2) {  // geographic
        uint16_t code = spec.epsg ? (uint16_t)spec.epsg : (uint16_t)32767;
        gks.push_back({2048, 0, 1, code});
        if (!spec.crs_citation.empty()) add_citation(1026, spec.crs_citation);
    } else {  // projected (default)
        uint16_t code = spec.epsg ? (uint16_t)spec.epsg : (uint16_t)32767;
        gks.push_back({3072, 0, 1, code});
        if (!spec.crs_citation.empty()) add_citation(3073, spec.crs_citation);
    }
    std::vector<uint16_t> gkdir;
    gkdir.push_back(1);  // KeyDirectoryVersion
    gkdir.push_back(1);  // KeyRevision
    gkdir.push_back(1);  // MinorRevision
    gkdir.push_back((uint16_t)gks.size());
    for (const auto& g : gks) {
        gkdir.push_back(g.id);
        gkdir.push_back(g.loc);
        gkdir.push_back(g.cnt);
        gkdir.push_back(g.val);
    }
    return gkdir;
}

// Build the TIFF field list for a single IFD (one resolution level). Tags are
// emitted in ascending tag order (TIFF 6.0 requirement); TileOffsets (324) is a
// placeholder patched once offsets are known. The geo / GDAL tags are attached
// only when `with_geo` is set (the full-resolution IFD).
std::vector<Field> make_level_fields(const CogSpec& spec, uint32_t w,
                                     uint32_t h, bool is_overview,
                                     bool with_geo,
                                     const std::vector<uint16_t>& gkdir,
                                     const std::string& ascii_pool,
                                     const std::vector<uint64_t>& bytecounts) {
    const uint16_t spp = spec.samples_per_pixel;
    std::vector<uint16_t> bps(spp, spec.bits_per_sample);
    std::vector<uint16_t> sfmt(spp, spec.sample_format);
    std::vector<uint16_t> extrasamples;  // 0 = unspecified
    for (int i = 1; i < spp; ++i) extrasamples.push_back(0);

    uint32_t tx = spec.tile_width, ty = spec.tile_height;
    uint32_t ntx = (w + tx - 1) / tx;
    uint32_t nty = (h + ty - 1) / ty;
    uint32_t ntiles = ntx * nty;

    std::vector<Field> f;
    auto addS = [&](uint16_t tag, const std::vector<uint16_t>& v) {
        f.push_back({tag, 3, (uint32_t)v.size(), ser_shorts(v)});
    };
    auto addL = [&](uint16_t tag, const std::vector<uint32_t>& v) {
        f.push_back({tag, 4, (uint32_t)v.size(), ser_longs(v)});
    };
    auto addD = [&](uint16_t tag, const std::vector<double>& v) {
        f.push_back({tag, 12, (uint32_t)v.size(), ser_doubles(v)});
    };
    auto addA = [&](uint16_t tag, const std::string& s) {
        std::string b = s;
        b.push_back('\0');
        f.push_back({tag, 2, (uint32_t)b.size(), b});
    };

    f.push_back(
        {254, 4, 1, ser_longs({is_overview ? 1u : 0u})});  // NewSubfileType
    addL(256, {w});                                        // ImageWidth
    addL(257, {h});                                        // ImageLength
    addS(258, bps);                                        // BitsPerSample
    addS(259, {spec.compression});                         // Compression
    addS(262, {1});    // Photometric=BlackIsZero
    addS(277, {spp});  // SamplesPerPixel
    addS(284, {1});    // PlanarConfig=chunky
    if (spec.compression == 8 && spec.predictor != 1)
        addS(317, {spec.predictor});  // Predictor
    addS(322, {(uint16_t)tx});        // TileWidth
    addS(323, {(uint16_t)ty});        // TileLength
    {
        std::vector<uint32_t> placeholder(ntiles, 0);
        addL(324, placeholder);  // TileOffsets (patched later)
    }
    {
        std::vector<uint32_t> bc(ntiles, 0);
        for (uint32_t t = 0; t < ntiles && t < bytecounts.size(); ++t)
            bc[t] = (uint32_t)bytecounts[t];
        addL(325, bc);  // TileByteCounts
    }
    if (spp > 1) addS(338, extrasamples);  // ExtraSamples
    addS(339, sfmt);                       // SampleFormat
    if (with_geo) {
        if (spec.has_pixel_scale)
            addD(33550, {spec.pixel_scale[0], spec.pixel_scale[1],
                         spec.pixel_scale[2]});
        if (spec.has_tiepoint)
            addD(33922, {spec.tiepoint[0], spec.tiepoint[1], spec.tiepoint[2],
                         spec.tiepoint[3], spec.tiepoint[4], spec.tiepoint[5]});
        addS(34735, gkdir);                                // GeoKeyDirectory
        if (!ascii_pool.empty()) addA(34737, ascii_pool);  // GeoAsciiParams
        std::string meta = build_gdal_metadata_xml(spec.meta_items);
        if (!meta.empty()) addA(42112, meta);  // GDAL_METADATA
        if (spec.has_nodata)
            addA(42113, format_gdal_nodata(spec.nodata));  // GDAL_NODATA
    }
    return f;
}

// Build the field list for every level (level 0 = full resolution, carrying the
// geo / GDAL tags; the rest are overview levels).
std::vector<std::vector<Field>> make_ifd_fields(
    const CogSpec& spec, const std::vector<uint32_t>& level_width,
    const std::vector<uint32_t>& level_height,
    const std::vector<std::vector<uint64_t>>& level_tile_bytecounts) {
    std::string ascii_pool;
    std::vector<uint16_t> gkdir = make_geokeys(spec, ascii_pool);
    const size_t nlev = level_width.size();
    std::vector<std::vector<Field>> out(nlev);
    for (size_t L = 0; L < nlev; ++L)
        out[L] = make_level_fields(spec, level_width[L], level_height[L],
                                   /*is_overview=*/L != 0, /*with_geo=*/L == 0,
                                   gkdir, ascii_pool, level_tile_bytecounts[L]);
    return out;
}

// Placement of one IFD within the header region.
struct Layout {
    uint64_t entry_block = 0;       // offset of the IFD entry block
    std::vector<int> external;      // 1 if field i is stored externally
    std::vector<uint64_t> ext_off;  // external offset of field i (if external)
};

// Lay out the IFD chain starting at `base_offset`. Fills `lay` and `ifd_start`
// and returns the end cursor (first free byte after the last external pool).
// Field byte layout is fixed, so the region size is known before tile offsets.
uint64_t layout_ifds(const std::vector<std::vector<Field>>& ifd_fields,
                     uint64_t base_offset, std::vector<Layout>& lay,
                     std::vector<uint64_t>& ifd_start) {
    const size_t nlev = ifd_fields.size();
    lay.assign(nlev, Layout{});
    ifd_start.assign(nlev, 0);
    uint64_t cursor = base_offset;
    for (size_t L = 0; L < nlev; ++L) {
        const auto& fields = ifd_fields[L];
        Layout lo;
        lo.entry_block = cursor;
        ifd_start[L] = cursor;
        uint64_t entry_sz = 2 + (uint64_t)fields.size() * 12 + 4;
        uint64_t ext_cursor = cursor + entry_sz;
        lo.external.assign(fields.size(), 0);
        lo.ext_off.assign(fields.size(), 0);
        for (size_t i = 0; i < fields.size(); ++i) {
            if (fields[i].bytes.size() > 4) {
                lo.external[i] = 1;
                ext_cursor = align2(ext_cursor);
                lo.ext_off[i] = ext_cursor;
                ext_cursor += fields[i].bytes.size();
            }
        }
        cursor = ext_cursor;
        lay[L] = lo;
    }
    return cursor;
}

// Overwrite the serialized bytes of the field with tag `tag` in `fields`.
void patch_field(std::vector<Field>& fields, uint16_t tag,
                 const std::string& bytes) {
    for (auto& fld : fields)
        if (fld.tag == tag) {
            fld.bytes = bytes;
            return;
        }
}

// Emit the IFD-chain bytes for the region [base_offset, region_end). Output
// index 0 corresponds to `base_offset`; external pools are padded to their
// assigned absolute offsets. The caller writes the 8-byte TIFF header (and any
// leading tile data) separately.
std::string emit_ifds(const std::vector<std::vector<Field>>& ifd_fields,
                      const std::vector<Layout>& lay,
                      const std::vector<uint64_t>& ifd_start,
                      uint64_t base_offset, uint64_t region_end) {
    const size_t nlev = ifd_fields.size();
    std::string out;
    out.reserve(region_end - base_offset);
    auto pad_to = [&](uint64_t abs) {
        while (out.size() + base_offset < abs) out.push_back('\0');
    };
    for (size_t L = 0; L < nlev; ++L) {
        const auto& fields = ifd_fields[L];
        const auto& lo = lay[L];
        pad_to(lo.entry_block);
        put_u16(out, (uint16_t)fields.size());
        for (size_t i = 0; i < fields.size(); ++i) {
            const Field& fld = fields[i];
            put_u16(out, fld.tag);
            put_u16(out, fld.type);
            put_u32(out, fld.count);
            if (lo.external[i]) {
                put_u32(out, (uint32_t)lo.ext_off[i]);
            } else {
                std::string v = fld.bytes;
                v.resize(4, '\0');
                out.append(v, 0, 4);
            }
        }
        // Next-IFD pointer (0 terminates the chain).
        put_u32(out, (uint32_t)(L + 1 < nlev ? ifd_start[L + 1] : 0));
        for (size_t i = 0; i < fields.size(); ++i) {
            if (lo.external[i]) {
                pad_to(lo.ext_off[i]);
                out += fields[i].bytes;
            }
        }
    }
    pad_to(region_end);
    return out;
}

}  // namespace

std::string build_cog_header(
    const CogSpec& spec, const std::vector<uint32_t>& level_width,
    const std::vector<uint32_t>& level_height,
    const std::vector<std::vector<uint64_t>>& level_tile_bytecounts,
    uint64_t& data_start, std::vector<uint64_t>& tile_offsets_flat) {
    const size_t nlev = level_width.size();
    auto ifd_fields =
        make_ifd_fields(spec, level_width, level_height, level_tile_bytecounts);
    std::vector<Layout> lay;
    std::vector<uint64_t> ifd_start;
    uint64_t region_end = layout_ifds(ifd_fields, 8, lay, ifd_start);
    data_start = align2(region_end);

    // Assign tile offsets sequentially from data_start and patch TileOffsets.
    tile_offsets_flat.clear();
    uint64_t dcur = data_start;
    for (size_t L = 0; L < nlev; ++L) {
        std::vector<uint32_t> offs;
        for (uint64_t bc : level_tile_bytecounts[L]) {
            offs.push_back((uint32_t)dcur);
            tile_offsets_flat.push_back(dcur);
            dcur += bc;
        }
        patch_field(ifd_fields[L], 324, ser_longs(offs));
    }

    // TIFF header ("II", 42, offset to first IFD) + the IFD chain, padded to
    // data_start so tiles start exactly where the header offsets point.
    std::string out = "II";
    put_u16(out, 42);
    put_u32(out, (uint32_t)ifd_start[0]);
    out += emit_ifds(ifd_fields, lay, ifd_start, 8, region_end);
    while (out.size() < data_start) out.push_back('\0');
    return out;
}

uint64_t cog_header_size(const CogSpec& spec,
                         const std::vector<uint32_t>& level_width,
                         const std::vector<uint32_t>& level_height) {
    // The TileByteCounts values don't affect the header size (the field is a
    // fixed one LONG per tile), so zero-filled counts of the right length give
    // the correct layout.
    std::vector<std::vector<uint64_t>> bytecounts(level_width.size());
    for (size_t L = 0; L < level_width.size(); ++L) {
        uint32_t ntx = (level_width[L] + spec.tile_width - 1) / spec.tile_width;
        uint32_t nty =
            (level_height[L] + spec.tile_height - 1) / spec.tile_height;
        bytecounts[L].assign((size_t)ntx * nty, 0);
    }
    auto ifd_fields =
        make_ifd_fields(spec, level_width, level_height, bytecounts);
    std::vector<Layout> lay;
    std::vector<uint64_t> ifd_start;
    uint64_t region_end = layout_ifds(ifd_fields, 8, lay, ifd_start);
    return align2(region_end);
}

std::string build_cog_header_fixed(
    const CogSpec& spec, const std::vector<uint32_t>& level_width,
    const std::vector<uint32_t>& level_height,
    const std::vector<std::vector<uint64_t>>& level_tile_offsets,
    const std::vector<std::vector<uint64_t>>& level_tile_bytecounts) {
    const size_t nlev = level_width.size();
    auto ifd_fields =
        make_ifd_fields(spec, level_width, level_height, level_tile_bytecounts);
    std::vector<Layout> lay;
    std::vector<uint64_t> ifd_start;
    uint64_t region_end = layout_ifds(ifd_fields, 8, lay, ifd_start);
    uint64_t data_start = align2(region_end);

    // Patch TileOffsets with the explicit (possibly out-of-order) offsets of
    // the already-written tiles.
    for (size_t L = 0; L < nlev; ++L) {
        std::vector<uint32_t> offs;
        offs.reserve(level_tile_offsets[L].size());
        for (uint64_t o : level_tile_offsets[L]) offs.push_back((uint32_t)o);
        patch_field(ifd_fields[L], 324, ser_longs(offs));
    }

    std::string out = "II";
    put_u16(out, 42);
    put_u32(out, (uint32_t)ifd_start[0]);
    out += emit_ifds(ifd_fields, lay, ifd_start, 8, region_end);
    while (out.size() < data_start) out.push_back('\0');
    return out;
}

std::string build_plain_ifd(const CogSpec& spec, uint32_t width,
                            uint32_t height,
                            const std::vector<uint64_t>& tile_offsets,
                            const std::vector<uint64_t>& tile_bytecounts,
                            uint64_t ifd_block_start) {
    std::vector<uint32_t> lw = {width};
    std::vector<uint32_t> lh = {height};
    std::vector<std::vector<uint64_t>> bc = {tile_bytecounts};
    auto ifd_fields = make_ifd_fields(spec, lw, lh, bc);
    std::vector<Layout> lay;
    std::vector<uint64_t> ifd_start;
    uint64_t region_end =
        layout_ifds(ifd_fields, ifd_block_start, lay, ifd_start);

    std::vector<uint32_t> offs;
    offs.reserve(tile_offsets.size());
    for (uint64_t o : tile_offsets) offs.push_back((uint32_t)o);
    patch_field(ifd_fields[0], 324, ser_longs(offs));

    // Just the IFD block (entries + external pool) placed at ifd_block_start;
    // the 8-byte TIFF header and tile data are written by the caller.
    return emit_ifds(ifd_fields, lay, ifd_start, ifd_block_start, region_end);
}

// --- Tile pack / overview down-sampling (COG pixel logic) -----------------
// These own the per-tile numeric work the Cython writer used to do in NumPy:
// padding + chunky interleaving of a tile and the nodata-aware 2x2 overview
// down-sample. Keeping them here (like the FlatGeobuf index builder) means the
// Cython layer only streams buffers and does file I/O.
namespace {

// Pad a chunky (h, w, spp) source to a full (th, tw, spp) tile, filling the
// edge with `nodata`. Returns the raw (uncompressed) tile bytes.
template <typename T>
std::string pad_interleave(const uint8_t* src, uint32_t h, uint32_t w,
                           uint32_t tw, uint32_t th, uint16_t spp, T nodata) {
    std::string raw;
    raw.resize((size_t)th * tw * spp * sizeof(T));
    T* dst = reinterpret_cast<T*>(&raw[0]);
    const T* s = reinterpret_cast<const T*>(src);
    for (uint32_t y = 0; y < th; ++y)
        for (uint32_t x = 0; x < tw; ++x)
            for (uint16_t c = 0; c < spp; ++c)
                dst[((size_t)y * tw + x) * spp + c] =
                    (y < h && x < w) ? s[((size_t)y * w + x) * spp + c]
                                     : nodata;
    return raw;
}

// Down-sample a chunky (h, w, spp) block by two into (oh, ow, spp). Floats are
// averaged over each 2x2 cell ignoring nodata (an all-nodata cell stays
// nodata); integer types are decimated (top-left sample).
template <typename T>
std::string downsample_chunky(const uint8_t* src, uint32_t h, uint32_t w,
                              uint16_t spp, bool is_float, T nodata,
                              bool has_nodata, uint32_t& oh, uint32_t& ow) {
    oh = (h + 1) / 2;
    ow = (w + 1) / 2;
    std::string raw;
    raw.resize((size_t)oh * ow * spp * sizeof(T));
    T* dst = reinterpret_cast<T*>(&raw[0]);
    const T* s = reinterpret_cast<const T*>(src);
    for (uint32_t oy = 0; oy < oh; ++oy) {
        for (uint32_t ox = 0; ox < ow; ++ox) {
            for (uint16_t c = 0; c < spp; ++c) {
                if (is_float) {
                    double sum = 0;
                    int cnt = 0;
                    for (uint32_t dy = 0; dy < 2; ++dy) {
                        uint32_t yy = 2 * oy + dy;
                        if (yy >= h) continue;
                        for (uint32_t dx = 0; dx < 2; ++dx) {
                            uint32_t xx = 2 * ox + dx;
                            if (xx >= w) continue;
                            T v = s[((size_t)yy * w + xx) * spp + c];
                            if (has_nodata && (double)v == (double)nodata)
                                continue;
                            sum += (double)v;
                            ++cnt;
                        }
                    }
                    dst[((size_t)oy * ow + ox) * spp + c] =
                        cnt ? (T)(sum / cnt) : (has_nodata ? nodata : (T)0);
                } else {
                    uint32_t yy = 2 * oy, xx = 2 * ox;
                    dst[((size_t)oy * ow + ox) * spp + c] =
                        (yy < h && xx < w) ? s[((size_t)yy * w + xx) * spp + c]
                                           : nodata;
                }
            }
        }
    }
    return raw;
}

// DEFLATE `raw` (level), or return it unchanged for compression != 8.
std::string maybe_deflate(const std::string& raw, uint16_t compression,
                          int level) {
    if (compression == 8)
        return deflate_block(reinterpret_cast<const uint8_t*>(raw.data()),
                             raw.size(), level);
    return raw;
}

}  // namespace

// Dispatch a templated call `EXPR(T)` on the (sample_format, bits) dtype.
#define FG_TYPED_DISPATCH(sample_format, bits, EXPR)           \
    (((sample_format) == 3 && (bits) == 32)   ? EXPR(float)    \
     : ((sample_format) == 3 && (bits) == 64) ? EXPR(double)   \
     : ((sample_format) == 2 && (bits) == 8)  ? EXPR(int8_t)   \
     : ((sample_format) == 2 && (bits) == 16) ? EXPR(int16_t)  \
     : ((sample_format) == 2 && (bits) == 32) ? EXPR(int32_t)  \
     : ((sample_format) == 1 && (bits) == 8)  ? EXPR(uint8_t)  \
     : ((sample_format) == 1 && (bits) == 16) ? EXPR(uint16_t) \
     : ((sample_format) == 1 && (bits) == 32) ? EXPR(uint32_t) \
                                              : EXPR(uint8_t))

std::string encode_tile(const uint8_t* src, uint32_t src_h, uint32_t src_w,
                        uint32_t tile_w, uint32_t tile_h, uint16_t spp,
                        uint16_t sample_format, uint16_t bits, double nodata,
                        uint8_t has_nodata, uint16_t compression, int level) {
    (void)has_nodata;
#define FG_PACK(T) \
    pad_interleave<T>(src, src_h, src_w, tile_w, tile_h, spp, (T)nodata)
    std::string raw = FG_TYPED_DISPATCH(sample_format, bits, FG_PACK);
#undef FG_PACK
    return maybe_deflate(raw, compression, level);
}

std::string downsample_tile(const uint8_t* src, uint32_t src_h, uint32_t src_w,
                            uint32_t tile_w, uint32_t tile_h, uint16_t spp,
                            uint16_t sample_format, uint16_t bits,
                            double nodata, uint8_t has_nodata,
                            uint16_t compression, int level) {
    bool is_float = (sample_format == 3);
    uint32_t oh = 0, ow = 0;
#define FG_DS(T)                                                      \
    downsample_chunky<T>(src, src_h, src_w, spp, is_float, (T)nodata, \
                         has_nodata != 0, oh, ow)
    std::string ds = FG_TYPED_DISPATCH(sample_format, bits, FG_DS);
#undef FG_DS
#define FG_PACK(T)                                                         \
    pad_interleave<T>(reinterpret_cast<const uint8_t*>(ds.data()), oh, ow, \
                      tile_w, tile_h, spp, (T)nodata)
    std::string raw = FG_TYPED_DISPATCH(sample_format, bits, FG_PACK);
#undef FG_PACK
    return maybe_deflate(raw, compression, level);
}

std::string downsample_raw(const uint8_t* src, uint32_t src_h, uint32_t src_w,
                           uint16_t spp, uint16_t sample_format, uint16_t bits,
                           double nodata, uint8_t has_nodata, uint32_t& out_h,
                           uint32_t& out_w) {
    bool is_float = (sample_format == 3);
#define FG_DS(T)                                                      \
    downsample_chunky<T>(src, src_h, src_w, spp, is_float, (T)nodata, \
                         has_nodata != 0, out_h, out_w)
    return FG_TYPED_DISPATCH(sample_format, bits, FG_DS);
#undef FG_DS
}

}  // namespace fiatgtiff
