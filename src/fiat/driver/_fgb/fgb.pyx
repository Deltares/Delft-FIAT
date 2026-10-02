# distutils: language = c++
# cython: language_level=3
"""Cython FlatGeobuf reader/writer bound to the vendored FlatGeobuf C++ sources.

This module provides the low-level building blocks used by the drop-in
``FlatGeobufDriver`` / ``FlatLayer`` API:

* :class:`Geometry` / :class:`Feature` - lightweight geometry + attribute holders.
* :class:`FlatGeobufReader` - sequential iteration and R-tree bbox selection.
* :class:`FlatGeobufWriter` - buffered append to a shared body file.
* :func:`finalize` - build the packed Hilbert R-tree and write the final ``.fgb``.

The heavy lifting (FlatBuffer (de)serialization and the packed R-tree) lives in the
vendored C++ sources; this module only marshals data to/from Python. The public
``FlatGeobufDriver`` / ``FlatLayer`` API is exposed from :mod:`fiat.driver.fgb`.
"""

import os

import numpy as np

from libc.stdint cimport int32_t, uint8_t, uint16_t, uint32_t, uint64_t
from libc.string cimport memcpy
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


# --- Constants ------------------------------------------------------------
MAGIC = b"\x66\x67\x62\x03\x66\x67\x62\x01"
cdef bytes _MAGIC = MAGIC
DEF _MAGIC_LEN = 8

# GeometryType enum (FlatGeobuf).
GT_UNKNOWN = 0
GT_POINT = 1
GT_LINESTRING = 2
GT_POLYGON = 3
GT_MULTIPOINT = 4
GT_MULTILINESTRING = 5
GT_MULTIPOLYGON = 6

# ColumnType enum (FlatGeobuf).
CT_BYTE = 0
CT_UBYTE = 1
CT_BOOL = 2
CT_SHORT = 3
CT_USHORT = 4
CT_INT = 5
CT_UINT = 6
CT_LONG = 7
CT_ULONG = 8
CT_FLOAT = 9
CT_DOUBLE = 10
CT_STRING = 11
CT_JSON = 12
CT_DATETIME = 13
CT_BINARY = 14


# --- Property (attribute) codec -------------------------------------------
cdef bytes _bytes_from_ptr(const uint8_t* p, size_t n):
    """Copy a C buffer into a Python bytes object."""
    return (<char*>p)[:n]


# Little-endian readers: pull a fixed-width value out of a (possibly unaligned)
# byte pointer. The bytes are assembled explicitly so the result is independent
# of the host's endianness, and floats go through a bit-preserving ``memcpy``.
cdef inline uint16_t _get_u16(const uint8_t* p) noexcept nogil:
    return <uint16_t>(p[0] | ((<uint16_t>p[1]) << 8))


cdef inline uint32_t _get_u32(const uint8_t* p) noexcept nogil:
    return ((<uint32_t>p[0]) | ((<uint32_t>p[1]) << 8) |
            ((<uint32_t>p[2]) << 16) | ((<uint32_t>p[3]) << 24))


cdef inline uint64_t _get_u64(const uint8_t* p) noexcept nogil:
    cdef uint64_t v = 0
    cdef int b
    for b in range(8):
        v |= (<uint64_t>p[b]) << (8 * b)
    return v


cdef inline float _get_f32(const uint8_t* p) noexcept nogil:
    cdef uint32_t u = _get_u32(p)
    cdef float f
    memcpy(&f, &u, 4)
    return f


cdef inline double _get_f64(const uint8_t* p) noexcept nogil:
    cdef uint64_t u = _get_u64(p)
    cdef double d
    memcpy(&d, &u, 8)
    return d


# Little-endian writers: append a fixed-width value to a growing byte vector,
# mirroring the readers above (explicit byte order, ``memcpy`` for floats).
cdef inline void _put_u16(vector[uint8_t]& buf, uint16_t v) noexcept nogil:
    buf.push_back(<uint8_t>v)
    buf.push_back(<uint8_t>(v >> 8))


cdef inline void _put_u32(vector[uint8_t]& buf, uint32_t v) noexcept nogil:
    cdef int s
    for s in range(0, 32, 8):
        buf.push_back(<uint8_t>(v >> s))


cdef inline void _put_u64(vector[uint8_t]& buf, uint64_t v) noexcept nogil:
    cdef int s
    for s in range(0, 64, 8):
        buf.push_back(<uint8_t>(v >> s))


cdef inline void _put_f32(vector[uint8_t]& buf, float v) noexcept nogil:
    cdef uint32_t u
    memcpy(&u, &v, 4)
    _put_u32(buf, u)


cdef inline void _put_f64(vector[uint8_t]& buf, double v) noexcept nogil:
    cdef uint64_t u
    memcpy(&u, &v, 8)
    _put_u64(buf, u)


cdef object _decode_properties(const uint8_t* p, size_t n, list col_types):
    """Decode a FlatGeobuf property blob into a list aligned with columns.

    The blob is a tight little-endian stream of ``(uint16 column index, value)``
    records, where the value width depends on the column's type. Fixed-width
    numbers are read straight off the byte pointer; strings/binary are
    length-prefixed (uint32).
    """
    cdef Py_ssize_t ncol = len(col_types)
    # Pre-fill with None so columns absent from the blob stay null.
    cdef list values = [None] * ncol
    cdef size_t off = 0
    cdef uint16_t col
    cdef int ctype
    cdef uint32_t slen
    # Walk record by record until the blob is exhausted.
    while off + 2 <= n:
        # Each record starts with the little-endian column index.
        col = _get_u16(p + off)
        off += 2
        # Defensive: stop on an out-of-range column index.
        if col >= ncol:
            break
        # Dispatch on the column's FlatGeobuf type and advance past its value.
        # Signed/float values are reinterpreted from their little-endian bits.
        ctype = <int>(<object>col_types[col])
        if ctype == CT_BYTE:
            values[col] = <signed char>p[off]
            off += 1
        elif ctype == CT_UBYTE:
            values[col] = p[off]
            off += 1
        elif ctype == CT_BOOL:
            values[col] = bool(p[off])
            off += 1
        elif ctype == CT_SHORT:
            values[col] = <short>_get_u16(p + off)
            off += 2
        elif ctype == CT_USHORT:
            values[col] = _get_u16(p + off)
            off += 2
        elif ctype == CT_INT:
            values[col] = <int>_get_u32(p + off)
            off += 4
        elif ctype == CT_UINT:
            values[col] = _get_u32(p + off)
            off += 4
        elif ctype == CT_LONG:
            values[col] = <long long>_get_u64(p + off)
            off += 8
        elif ctype == CT_ULONG:
            values[col] = _get_u64(p + off)
            off += 8
        elif ctype == CT_FLOAT:
            values[col] = _get_f32(p + off)
            off += 4
        elif ctype == CT_DOUBLE:
            values[col] = _get_f64(p + off)
            off += 8
        elif ctype == CT_STRING or ctype == CT_JSON or ctype == CT_DATETIME:
            # Length-prefixed UTF-8 text.
            slen = _get_u32(p + off)
            off += 4
            values[col] = (<char*>(p + off))[:slen].decode("utf-8")
            off += slen
        elif ctype == CT_BINARY:
            slen = _get_u32(p + off)
            off += 4
            values[col] = (<char*>(p + off))[:slen]
            off += slen
        else:
            break
    return values


cdef bytes _encode_properties(list values, list col_types):
    """Encode a list of column values into a FlatGeobuf property blob.

    The inverse of :func:`_decode_properties`: each non-null value is written as
    ``(uint16 column index, little-endian value)``. Null values are skipped
    entirely (their column index simply never appears in the blob).
    """
    cdef vector[uint8_t] buf
    cdef Py_ssize_t i, n = len(values)
    cdef int ctype
    cdef bytes enc
    cdef const uint8_t* ep
    cdef uint8_t bval = 0
    for i in range(n):
        v = values[i]
        # Skip nulls; the decoder defaults missing columns back to None.
        if v is None:
            continue
        # Write the column index, then the value in the column's native width.
        # Each value is cast through its matching C type so signed/unsigned and
        # overflow semantics line up with the FlatGeobuf column type.
        ctype = <int>(<object>col_types[i])
        _put_u16(buf, <uint16_t>i)
        if ctype == CT_BOOL:
            bval = 1 if v else 0
            buf.push_back(bval)
        elif ctype == CT_BYTE:
            buf.push_back(<uint8_t><signed char>(<int>v))
        elif ctype == CT_UBYTE:
            buf.push_back(<uint8_t>(<unsigned int>v))
        elif ctype == CT_SHORT:
            _put_u16(buf, <uint16_t>(<int>v))
        elif ctype == CT_USHORT:
            _put_u16(buf, <uint16_t>(<unsigned int>v))
        elif ctype == CT_INT:
            _put_u32(buf, <uint32_t>(<int>v))
        elif ctype == CT_UINT:
            _put_u32(buf, <uint32_t>(<unsigned int>v))
        elif ctype == CT_LONG:
            _put_u64(buf, <uint64_t>(<long long>v))
        elif ctype == CT_ULONG:
            _put_u64(buf, <uint64_t>(<unsigned long long>v))
        elif ctype == CT_FLOAT:
            _put_f32(buf, <float>v)
        elif ctype == CT_DOUBLE:
            _put_f64(buf, <double>v)
        elif ctype == CT_STRING or ctype == CT_JSON or ctype == CT_DATETIME:
            # Length-prefixed UTF-8 text.
            enc = str(v).encode("utf-8")
            _put_u32(buf, <uint32_t>len(enc))
            ep = <const uint8_t*><char*>enc
            buf.insert(buf.end(), ep, ep + len(enc))
        elif ctype == CT_BINARY:
            enc = bytes(v)
            _put_u32(buf, <uint32_t>len(enc))
            ep = <const uint8_t*><char*>enc
            buf.insert(buf.end(), ep, ep + len(enc))
    # Hand back the contiguous blob (empty bytes when nothing was written).
    if buf.size() == 0:
        return b""
    return _bytes_from_ptr(buf.data(), buf.size())


# --- Geometry / Feature ---------------------------------------------------
cdef class Geometry:
    """A 2D geometry as flat coordinate arrays plus ring/part boundaries.

    Attributes
    ----------
    type : int
        FlatGeobuf ``GeometryType`` value.
    xy : np.ndarray
        Flat interleaved x, y coordinates (``float64``).
    ends : np.ndarray
        Cumulative coordinate-pair counts marking the end of each ring/line
        (``uint32``). Empty for points / linestrings.
    parts : np.ndarray
        Cumulative ring counts marking the end of each polygon in a
        MultiPolygon (``uint32``). Empty otherwise.
    """

    cdef public int type
    cdef public object xy
    cdef public object ends
    cdef public object parts
    cdef public double minx
    cdef public double miny
    cdef public double maxx
    cdef public double maxy
    cdef public bint is_empty

    def envelope(self):
        """Return ``(minx, miny, maxx, maxy)``."""
        return (self.minx, self.miny, self.maxx, self.maxy)

    @property
    def coords(self):
        """Return the coordinates reshaped to ``(n, 2)``."""
        return np.asarray(self.xy, dtype=np.float64).reshape(-1, 2)


cdef Geometry _make_geometry(GeometryResult* g):
    """Copy a C++ ``GeometryResult`` into a Python :class:`Geometry`.

    The flat C++ vectors are bulk-copied into fresh numpy arrays so the Python
    object owns its own memory (the C++ struct is transient and reused).
    """
    cdef Geometry geom = Geometry.__new__(Geometry)
    cdef Py_ssize_t n = g.xy.size()
    cdef Py_ssize_t ne = g.ends.size()
    cdef Py_ssize_t npart = g.parts.size()
    # Allocate the destination numpy arrays.
    cdef object xy = np.empty(n, dtype=np.float64)
    cdef object ends = np.empty(ne, dtype=np.uint32)
    cdef object parts = np.empty(npart, dtype=np.uint32)
    # Typed memoryviews over the destinations (None when empty).
    cdef double[::1] xy_v = xy if n else None
    cdef uint32_t[::1] ends_v = ends if ne else None
    cdef uint32_t[::1] parts_v = parts if npart else None
    # Bulk-copy each vector straight into its contiguous numpy buffer.
    if n:
        memcpy(&xy_v[0], g.xy.data(), n * sizeof(double))
    if ne:
        memcpy(&ends_v[0], g.ends.data(), ne * sizeof(uint32_t))
    if npart:
        memcpy(&parts_v[0], g.parts.data(), npart * sizeof(uint32_t))
    # Transfer the scalar metadata (type, bounding box, emptiness).
    geom.type = g.geometry_type
    geom.xy = xy
    geom.ends = ends
    geom.parts = parts
    geom.minx = g.minx
    geom.miny = g.miny
    geom.maxx = g.maxx
    geom.maxy = g.maxy
    geom.is_empty = bool(g.empty)
    return geom


def make_geometry(int geom_type, xy, ends=None, parts=None):
    """Build a :class:`Geometry` from flat coordinate arrays.

    Parameters
    ----------
    geom_type : int
        FlatGeobuf ``GeometryType`` code.
    xy : array-like
        Flat interleaved x, y coordinates.
    ends : array-like, optional
        Cumulative coordinate-pair counts per ring/line.
    parts : array-like, optional
        Cumulative ring counts per polygon (MultiPolygon).
    """
    cdef Geometry geom = Geometry.__new__(Geometry)
    xy_arr = np.ascontiguousarray(xy, dtype=np.float64).ravel()
    ends_arr = np.ascontiguousarray(
        [] if ends is None else ends, dtype=np.uint32).ravel()
    parts_arr = np.ascontiguousarray(
        [] if parts is None else parts, dtype=np.uint32).ravel()
    geom.type = geom_type
    geom.xy = xy_arr
    geom.ends = ends_arr
    geom.parts = parts_arr
    coords = xy_arr.reshape(-1, 2)
    if coords.shape[0]:
        geom.minx = float(coords[:, 0].min())
        geom.miny = float(coords[:, 1].min())
        geom.maxx = float(coords[:, 0].max())
        geom.maxy = float(coords[:, 1].max())
        geom.is_empty = False
    else:
        geom.minx = geom.miny = geom.maxx = geom.maxy = 0.0
        geom.is_empty = True
    return geom


cdef class Feature:
    """A single feature: a :class:`Geometry` and a list of attribute values."""

    cdef public Geometry geometry
    cdef public list values
    cdef public object _columns  # dict name -> index (shared, may be None)

    def get_field(self, key):
        """Return an attribute value by column index or name."""
        # Integer index is the hot path; only strings need the name lookup.
        if isinstance(key, str):
            if self._columns is None:
                raise KeyError(key)
            return self.values[self._columns[key]]
        return self.values[key]

    def __getitem__(self, key):
        return self.get_field(key)

    def geometry_ref(self):
        """Return the feature geometry (OGR-compat alias)."""
        return self.geometry


# --- Reader ---------------------------------------------------------------
cdef class FlatGeobufReader:
    """Read a FlatGeobuf file: header metadata, iteration and bbox selection."""

    cdef bytes _data
    cdef const uint8_t* _ptr
    cdef size_t _len
    cdef size_t _feature_start
    cdef size_t _index_start
    cdef size_t _index_len
    cdef readonly str name
    cdef readonly int geometry_type
    cdef readonly unsigned long long features_count
    cdef readonly int index_node_size
    cdef readonly list col_names
    cdef readonly list col_types
    cdef readonly str crs_wkt
    cdef readonly str crs_org
    cdef readonly int crs_code
    cdef readonly object envelope
    cdef readonly dict columns

    def __cinit__(self, path):
        cdef HeaderResult hr
        cdef size_t consumed
        cdef size_t off
        # Read the whole file into memory once; parsing is all zero-copy views
        # over this buffer (features are seeked into by byte offset).
        with open(path, "rb") as fh:
            self._data = fh.read()
        self._len = len(self._data)
        self._ptr = <const uint8_t*><char*>self._data
        # Validate the FlatGeobuf magic bytes (first 3 bytes spell "fgb").
        if self._len < _MAGIC_LEN or self._data[:3] != _MAGIC[:3]:
            raise ValueError(f"{path} is not a FlatGeobuf file")

        # Parse the header (skipping the 8 magic bytes) via the C++ layer.
        consumed = parse_header(self._ptr + _MAGIC_LEN, self._len - _MAGIC_LEN, hr)
        if consumed == 0:
            raise ValueError(f"Could not parse FlatGeobuf header in {path}")

        # Copy the header metadata into readonly Python attributes.
        self.name = hr.name.decode("utf-8") if hr.name.size() else ""
        self.geometry_type = hr.geometry_type
        self.features_count = hr.features_count
        self.index_node_size = hr.index_node_size
        self.col_names = [hr.col_names[i].decode("utf-8")
                          for i in range(hr.col_names.size())]
        self.col_types = [int(hr.col_types[i]) for i in range(hr.col_types.size())]
        self.crs_wkt = hr.crs_wkt.decode("utf-8") if hr.crs_wkt.size() else ""
        self.crs_org = hr.crs_org.decode("utf-8") if hr.crs_org.size() else ""
        self.crs_code = hr.crs_code
        # name -> index lookup for attribute access by column name.
        self.columns = {n: i for i, n in enumerate(self.col_names)}
        if hr.has_envelope:
            self.envelope = (hr.env_minx, hr.env_miny, hr.env_maxx, hr.env_maxy)
        else:
            self.envelope = None

        # Locate the sections: magic + header, then the optional R-tree index,
        # then the feature data. index_node_size == 0 means no index is present.
        off = _MAGIC_LEN + consumed
        self._index_start = off
        self._index_len = 0
        if self.index_node_size > 0 and self.features_count > 0:
            # The index byte size is a pure function of count and node size,
            # so we can skip past it without parsing it.
            self._index_len = index_size(self.features_count, self.index_node_size)
            off += self._index_len
        self._feature_start = off

    cdef Feature _feature_from(self, GeometryResult* g, string* props):
        """Build a :class:`Feature` from a parsed geometry + raw property blob."""
        cdef Feature ft = Feature.__new__(Feature)
        ft.geometry = _make_geometry(g)
        # Decode the attribute values, or fill with None when there are none.
        if props.size() > 0:
            ft.values = _decode_properties(<const uint8_t*>props.data(),
                                           props.size(), self.col_types)
        else:
            ft.values = [None] * len(self.col_types)
        # Share the column lookup so features can be indexed by name.
        ft._columns = self.columns
        return ft

    cdef Feature _read_feature_at(self, size_t off):
        """Parse a single feature at byte ``off`` (used by the R-tree search)."""
        cdef GeometryResult g
        cdef string props
        cdef size_t consumed = parse_feature(self._ptr + off, self._len - off,
                                             g, props)
        if consumed == 0:
            return None
        return self._feature_from(&g, &props)

    def __len__(self):
        return int(self.features_count)

    def __iter__(self):
        # Sequentially walk the feature section: parse one feature, advance by
        # its byte length, repeat. The C++ struct is reused (cleared) each time.
        cdef size_t off = self._feature_start
        cdef GeometryResult g
        cdef string props
        cdef size_t consumed
        while off < self._len:
            # Reset the reused result struct before the next parse.
            g.xy.clear()
            g.ends.clear()
            g.parts.clear()
            g.empty = 1
            props.clear()
            consumed = parse_feature(self._ptr + off, self._len - off, g, props)
            if consumed == 0:
                break
            off += consumed
            yield self._feature_from(&g, &props)

    def reduced_iter(self, long si, long ei):
        """Yield features whose 1-based position lies in ``[si, ei]``."""
        cdef long c = 1
        for ft in self:
            if si <= c <= ei:
                yield ft
            elif c > ei:
                # Past the requested range; no need to parse the rest.
                break
            c += 1

    def select(self, double minx, double miny, double maxx, double maxy):
        """Yield features intersecting a bounding box using the R-tree.

        Falls back to a full scan with an envelope test if the file has no index.
        """
        cdef vector[uint64_t] offsets
        cdef Feature ft
        cdef size_t i
        if self._index_len > 0:
            # Fast path: ask the packed R-tree for the matching feature offsets,
            # then seek/parse just those features.
            offsets = search_index(self._ptr + self._index_start,
                                   self._index_len, self.features_count,
                                   self.index_node_size, minx, miny, maxx, maxy)
            for i in range(offsets.size()):
                ft = self._read_feature_at(self._feature_start + offsets[i])
                if ft is not None:
                    yield ft
        else:
            # No index: scan everything and reject by bounding-box overlap.
            for ft in self:
                g = ft.geometry
                if not (g.maxx < minx or g.minx > maxx or
                        g.maxy < miny or g.miny > maxy):
                    yield ft

    def bbox_iter(self, bbox):
        """Alias for :meth:`select` taking a ``(minx, miny, maxx, maxy)`` tuple."""
        return self.select(bbox[0], bbox[1], bbox[2], bbox[3])


# --- Writer ---------------------------------------------------------------
cdef tuple _feature_bytes(int geom_type, object xy, object ends, object parts,
                          bytes props):
    """Serialize one feature and report its envelope in a single pass.

    Marshals the numpy geometry arrays + encoded property blob into C++ vectors
    and hands them to ``build_feature``. While copying the interleaved
    coordinates it also accumulates the bounding box, so the writer does not
    need a separate numpy pass over ``xy`` to record the feature envelope.

    Returns ``(buf, minx, miny, maxx, maxy)``.
    """
    cdef vector[double] cxy
    cdef vector[uint32_t] cends
    cdef vector[uint32_t] cparts
    cdef vector[uint8_t] cprops
    cdef Py_ssize_t n, ne, npart, nprops
    cdef double[::1] xy_v = np.ascontiguousarray(xy, dtype=np.float64).ravel()
    cdef uint32_t[::1] ends_v
    cdef uint32_t[::1] parts_v
    cdef double minx = 0.0, miny = 0.0, maxx = 0.0, maxy = 0.0
    cdef double x, y
    cdef Py_ssize_t i

    # Bulk-copy the interleaved coordinates and fold in the bounding box.
    n = xy_v.shape[0]
    if n:
        cxy.resize(n)
        memcpy(cxy.data(), &xy_v[0], n * sizeof(double))
        minx = maxx = xy_v[0]
        miny = maxy = xy_v[1]
        for i in range(2, n, 2):
            x = xy_v[i]
            y = xy_v[i + 1]
            if x < minx:
                minx = x
            elif x > maxx:
                maxx = x
            if y < miny:
                miny = y
            elif y > maxy:
                maxy = y
    # Ring ends (optional, e.g. absent for a single point).
    if ends is not None and len(ends):
        ends_v = np.ascontiguousarray(ends, dtype=np.uint32).ravel()
        ne = ends_v.shape[0]
        cends.resize(ne)
        memcpy(cends.data(), &ends_v[0], ne * sizeof(uint32_t))
    # Part boundaries (only MultiPolygon).
    if parts is not None and len(parts):
        parts_v = np.ascontiguousarray(parts, dtype=np.uint32).ravel()
        npart = parts_v.shape[0]
        cparts.resize(npart)
        memcpy(cparts.data(), &parts_v[0], npart * sizeof(uint32_t))
    # The already-encoded attribute blob.
    nprops = len(props)
    if nprops:
        cprops.resize(nprops)
        memcpy(cprops.data(), <const uint8_t*><char*>props, nprops)
    cdef string out = build_feature(<uint8_t>geom_type, cxy, cends, cparts, cprops)
    return (_bytes_from_ptr(<const uint8_t*>out.data(), out.size()),
            minx, miny, maxx, maxy)


class FlatGeobufWriter:
    """Buffered FlatGeobuf writer.

    Features are appended (as size-prefixed FlatBuffers) to a shared *body* file;
    envelopes and byte offsets are recorded. A separate :func:`finalize` pass
    builds the packed Hilbert R-tree and writes the final indexed ``.fgb``.

    To benefit from multiprocessing, serialized features are first accumulated in
    an in-memory buffer and only flushed to the shared body file once the buffer
    exceeds ``buffer_size`` bytes (or on :meth:`close`). Each flush takes the
    optional lock once for a whole block of features instead of once per feature,
    which greatly reduces lock contention between worker processes.

    Parameters
    ----------
    path : str
        Output ``.fgb`` path (the body file is ``path + '.body'``).
    col_names, col_types : list
        Column names and FlatGeobuf ``ColumnType`` codes.
    geom_type : int
        FlatGeobuf ``GeometryType`` code.
    name : str, optional
        Layer name.
    crs_wkt, crs_org, crs_code : optional
        Coordinate reference system metadata.
    node_size : int
        R-tree node size (default 16).
    lock : optional
        A multiprocessing lock guarding appends to the shared body file.
    buffer_size : int, optional
        In-memory buffer threshold in bytes. The buffer is flushed to the body
        file once the accumulated serialized features reach this size. Defaults
        to 50 MiB.
    """

    def __init__(self, path, col_names, col_types, geom_type, name="",
                 crs_wkt="", crs_org="", crs_code=0, node_size=16, lock=None,
                 buffer_size=50 * 1024 * 1024):
        self.path = os.fspath(path)
        self.body_path = self.path + ".body"
        self.name = name or ""
        self.col_names = list(col_names)
        self.col_types = list(col_types)
        self.geom_type = int(geom_type)
        self.crs_wkt = crs_wkt or ""
        self.crs_org = crs_org or ""
        self.crs_code = int(crs_code or 0)
        self.node_size = int(node_size)
        self.lock = lock
        self.buffer_size = int(buffer_size)
        self.records = []  # (minx, miny, maxx, maxy, offset, length)
        self._buffer = bytearray()  # accumulated serialized features
        # Pending records for buffered features: (minx, miny, maxx, maxy,
        # local_offset, length). local_offset is relative to the buffer start
        # and resolved to an absolute body offset on flush.
        self._pending = []
        self._body = open(self.body_path, "ab")

    def add_feature(self, xy, ends=None, parts=None, values=None):
        """Append one feature to the in-memory buffer.

        The feature is serialized and appended to the in-memory buffer (no lock,
        no file I/O). Its envelope + buffer-local offset + length are recorded so
        the pending records can be resolved to absolute body offsets when the
        buffer is flushed. The buffer is flushed to the shared body file once it
        exceeds ``buffer_size`` bytes.
        """
        # Encode the attributes, then serialize the whole feature. Serialization
        # also returns the geometry envelope, computed in the same pass.
        props = _encode_properties(list(values), self.col_types) if values else b""
        buf, minx, miny, maxx, maxy = _feature_bytes(
            self.geom_type, xy, ends, parts, props)
        # Append to the in-memory buffer, remembering the buffer-local offset.
        local_offset = len(self._buffer)
        self._buffer += buf
        self._pending.append((minx, miny, maxx, maxy, local_offset, len(buf)))
        # Flush once the buffer grows past the configured threshold.
        if len(self._buffer) >= self.buffer_size:
            self._flush()

    def _flush(self):
        """Flush the in-memory buffer to the shared body file.

        Takes the optional lock once for the whole block, appends the buffer to
        the body file and resolves every pending feature's buffer-local offset to
        an absolute body offset for the finalize pass.
        """
        if not self._pending:
            return
        # Serialize appends across processes with the lock (if provided).
        if self.lock is not None:
            self.lock.acquire()
        try:
            self._body.seek(0, os.SEEK_END)
            base = self._body.tell()
            self._body.write(self._buffer)
            self._body.flush()
        finally:
            if self.lock is not None:
                self.lock.release()
        # Resolve buffer-local offsets to absolute body offsets.
        for minx, miny, maxx, maxy, local_offset, length in self._pending:
            self.records.append((minx, miny, maxx, maxy, base + local_offset,
                                 length))
        self._buffer = bytearray()
        self._pending = []

    def close(self):
        """Flush any buffered features and close the body file handle."""
        if self._body is not None:
            self._flush()
            self._body.flush()
            self._body.close()
            self._body = None

    def finalize(self):
        """Finalize a single-writer file (build index + write output)."""
        # Flush the body, then hand our own records to the finalize routine.
        self.close()
        finalize(self.path, self.body_path, self.name, self.geom_type,
                 self.col_names, self.col_types, self.records, self.crs_wkt,
                 self.crs_org, self.crs_code, self.node_size)


def finalize(path, body_path, name, geom_type, col_names, col_types, records,
             crs_wkt="", crs_org="", crs_code=0, node_size=16):
    """Build the R-tree and write the final indexed FlatGeobuf file.

    Parameters
    ----------
    path : str
        Output ``.fgb`` path.
    body_path : str
        Path to the concatenated feature body written by the writer(s).
    name : str
        Layer name.
    geom_type : int
        FlatGeobuf ``GeometryType`` code.
    col_names, col_types : list
        Column metadata.
    records : list of tuple
        ``(minx, miny, maxx, maxy, body_offset, length)`` per feature.
    crs_wkt, crs_org, crs_code : optional
        CRS metadata.
    node_size : int
        R-tree node size.
    """
    cdef Py_ssize_t n = len(records)
    cdef vector[double] env_all
    cdef vector[double] env_ordered
    cdef vector[uint64_t] new_offsets
    cdef double extent[4]
    cdef vector[uint64_t] order
    cdef Py_ssize_t i
    cdef unsigned long long idx
    cdef unsigned long long running = 0
    cdef list ordered_records
    cdef string index
    cdef string header

    # Encode the layer name and CRS strings once.
    cdef string cname = name.encode("utf-8")
    cdef string cwkt = crs_wkt.encode("utf-8")
    cdef string corg = crs_org.encode("utf-8")

    # Marshal the column metadata into C++ vectors.
    cdef vector[string] cnames
    cdef vector[uint8_t] ctypes
    for nm in col_names:
        cnames.push_back(nm.encode("utf-8"))
    for ct in col_types:
        ctypes.push_back(<uint8_t>int(ct))

    if n == 0:
        # Empty layer: write a header with no index and delete the body file.
        header = build_header(cname, <uint8_t>geom_type, cnames, ctypes, 0,
                              <uint16_t>node_size, 0, 0, 0, 0, 0, corg,
                              <int32_t>crs_code, cwkt)
        with open(path, "wb") as out:
            out.write(_MAGIC)
            out.write(_bytes_from_ptr(<const uint8_t*>header.data(), header.size()))
        if os.path.exists(body_path):
            os.remove(body_path)
        return

    # Gather every feature's envelope (4 doubles each) for the Hilbert sort.
    for i in range(n):
        rec = records[i]
        env_all.push_back(rec[0])
        env_all.push_back(rec[1])
        env_all.push_back(rec[2])
        env_all.push_back(rec[3])

    # Sort feature indices along the Hilbert curve and get the total extent.
    order = hilbert_order(env_all, &extent[0])

    # Walk features in Hilbert order, computing each one's NEW byte offset in
    # the reordered output and collecting the ordered envelopes for the index.
    ordered_records = [None] * n
    for i in range(n):
        idx = order[i]
        rec = records[idx]
        env_ordered.push_back(rec[0])
        env_ordered.push_back(rec[1])
        env_ordered.push_back(rec[2])
        env_ordered.push_back(rec[3])
        new_offsets.push_back(running)
        ordered_records[i] = rec
        running += rec[5]  # rec[5] == feature byte length

    # Build the packed R-tree over the ordered envelopes + new offsets, and a
    # header that advertises the index and the total layer envelope.
    index = build_index(env_ordered, new_offsets, &extent[0], <uint16_t>node_size)
    header = build_header(cname, <uint8_t>geom_type, cnames, ctypes,
                          <uint64_t>n, <uint16_t>node_size, 1, extent[0],
                          extent[1], extent[2], extent[3], corg,
                          <int32_t>crs_code, cwkt)

    # Write the final file: magic + header + index + Hilbert-ordered features
    # (each copied back from the body file by its original offset/length).
    with open(body_path, "rb") as body, open(path, "wb") as out:
        out.write(_MAGIC)
        out.write(_bytes_from_ptr(<const uint8_t*>header.data(), header.size()))
        out.write(_bytes_from_ptr(<const uint8_t*>index.data(), index.size()))
        for i in range(n):
            rec = ordered_records[i]
            body.seek(rec[4])          # rec[4] == body offset
            out.write(body.read(rec[5]))

    # The temporary body file is no longer needed.
    if os.path.exists(body_path):
        os.remove(body_path)
