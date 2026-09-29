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
import struct as _struct

import numpy as np

from libc.stdint cimport int32_t, uint8_t, uint16_t, uint32_t, uint64_t
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


cdef object _decode_properties(const uint8_t* p, size_t n, list col_types):
    """Decode a FlatGeobuf property blob into a list aligned with columns."""
    cdef Py_ssize_t ncol = len(col_types)
    cdef list values = [None] * ncol
    cdef size_t off = 0
    cdef uint16_t col
    cdef int ctype
    cdef uint32_t slen
    py = _bytes_from_ptr(p, n)
    while off + 2 <= n:
        col = <uint16_t>(p[off] | (p[off + 1] << 8))
        off += 2
        if col >= ncol:
            break
        ctype = <int>(<object>col_types[col])
        if ctype == CT_BYTE:
            values[col] = _struct.unpack_from("<b", py, off)[0]
            off += 1
        elif ctype == CT_UBYTE:
            values[col] = p[off]
            off += 1
        elif ctype == CT_BOOL:
            values[col] = bool(p[off])
            off += 1
        elif ctype == CT_SHORT:
            values[col] = _struct.unpack_from("<h", py, off)[0]
            off += 2
        elif ctype == CT_USHORT:
            values[col] = _struct.unpack_from("<H", py, off)[0]
            off += 2
        elif ctype == CT_INT:
            values[col] = _struct.unpack_from("<i", py, off)[0]
            off += 4
        elif ctype == CT_UINT:
            values[col] = _struct.unpack_from("<I", py, off)[0]
            off += 4
        elif ctype == CT_LONG:
            values[col] = _struct.unpack_from("<q", py, off)[0]
            off += 8
        elif ctype == CT_ULONG:
            values[col] = _struct.unpack_from("<Q", py, off)[0]
            off += 8
        elif ctype == CT_FLOAT:
            values[col] = _struct.unpack_from("<f", py, off)[0]
            off += 4
        elif ctype == CT_DOUBLE:
            values[col] = _struct.unpack_from("<d", py, off)[0]
            off += 8
        elif ctype == CT_STRING or ctype == CT_JSON or ctype == CT_DATETIME:
            slen = _struct.unpack_from("<I", py, off)[0]
            off += 4
            values[col] = py[off:off + slen].decode("utf-8")
            off += slen
        elif ctype == CT_BINARY:
            slen = _struct.unpack_from("<I", py, off)[0]
            off += 4
            values[col] = bytes(py[off:off + slen])
            off += slen
        else:
            break
    return values


cdef bytes _encode_properties(list values, list col_types):
    """Encode a list of column values into a FlatGeobuf property blob."""
    cdef list out = []
    cdef Py_ssize_t i
    cdef int ctype
    for i in range(len(values)):
        v = values[i]
        if v is None:
            continue
        ctype = <int>(<object>col_types[i])
        out.append(_struct.pack("<H", i))
        if ctype == CT_BOOL:
            out.append(_struct.pack("<B", 1 if v else 0))
        elif ctype == CT_BYTE:
            out.append(_struct.pack("<b", int(v)))
        elif ctype == CT_UBYTE:
            out.append(_struct.pack("<B", int(v)))
        elif ctype == CT_SHORT:
            out.append(_struct.pack("<h", int(v)))
        elif ctype == CT_USHORT:
            out.append(_struct.pack("<H", int(v)))
        elif ctype == CT_INT:
            out.append(_struct.pack("<i", int(v)))
        elif ctype == CT_UINT:
            out.append(_struct.pack("<I", int(v)))
        elif ctype == CT_LONG:
            out.append(_struct.pack("<q", int(v)))
        elif ctype == CT_ULONG:
            out.append(_struct.pack("<Q", int(v)))
        elif ctype == CT_FLOAT:
            out.append(_struct.pack("<f", float(v)))
        elif ctype == CT_DOUBLE:
            out.append(_struct.pack("<d", float(v)))
        elif ctype == CT_STRING or ctype == CT_JSON or ctype == CT_DATETIME:
            enc = str(v).encode("utf-8")
            out.append(_struct.pack("<I", len(enc)))
            out.append(enc)
        elif ctype == CT_BINARY:
            enc = bytes(v)
            out.append(_struct.pack("<I", len(enc)))
            out.append(enc)
    return b"".join(out)


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
    cdef Geometry geom = Geometry.__new__(Geometry)
    cdef Py_ssize_t n = g.xy.size()
    cdef Py_ssize_t ne = g.ends.size()
    cdef Py_ssize_t npart = g.parts.size()
    cdef object xy = np.empty(n, dtype=np.float64)
    cdef object ends = np.empty(ne, dtype=np.uint32)
    cdef object parts = np.empty(npart, dtype=np.uint32)
    cdef double[::1] xy_v = xy if n else None
    cdef uint32_t[::1] ends_v = ends if ne else None
    cdef uint32_t[::1] parts_v = parts if npart else None
    cdef Py_ssize_t i
    for i in range(n):
        xy_v[i] = g.xy[i]
    for i in range(ne):
        ends_v[i] = g.ends[i]
    for i in range(npart):
        parts_v[i] = g.parts[i]
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
        cdef Py_ssize_t idx
        if isinstance(key, str):
            if self._columns is None:
                raise KeyError(key)
            idx = self._columns[key]
        else:
            idx = key
        return self.values[idx]

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
        with open(path, "rb") as fh:
            self._data = fh.read()
        self._len = len(self._data)
        self._ptr = <const uint8_t*><char*>self._data
        if self._len < _MAGIC_LEN or self._data[:3] != _MAGIC[:3]:
            raise ValueError(f"{path} is not a FlatGeobuf file")

        consumed = parse_header(self._ptr + _MAGIC_LEN, self._len - _MAGIC_LEN, hr)
        if consumed == 0:
            raise ValueError(f"Could not parse FlatGeobuf header in {path}")

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
        self.columns = {n: i for i, n in enumerate(self.col_names)}
        if hr.has_envelope:
            self.envelope = (hr.env_minx, hr.env_miny, hr.env_maxx, hr.env_maxy)
        else:
            self.envelope = None

        off = _MAGIC_LEN + consumed
        self._index_start = off
        self._index_len = 0
        if self.index_node_size > 0 and self.features_count > 0:
            self._index_len = index_size(self.features_count, self.index_node_size)
            off += self._index_len
        self._feature_start = off

    cdef Feature _feature_from(self, GeometryResult* g, string* props):
        cdef Feature ft = Feature.__new__(Feature)
        ft.geometry = _make_geometry(g)
        if props.size() > 0:
            ft.values = _decode_properties(<const uint8_t*>props.data(),
                                           props.size(), self.col_types)
        else:
            ft.values = [None] * len(self.col_types)
        ft._columns = self.columns
        return ft

    cdef Feature _read_feature_at(self, size_t off):
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
        cdef size_t off = self._feature_start
        cdef GeometryResult g
        cdef string props
        cdef size_t consumed
        while off < self._len:
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
            offsets = search_index(self._ptr + self._index_start,
                                   self._index_len, self.features_count,
                                   self.index_node_size, minx, miny, maxx, maxy)
            for i in range(offsets.size()):
                ft = self._read_feature_at(self._feature_start + offsets[i])
                if ft is not None:
                    yield ft
        else:
            for ft in self:
                g = ft.geometry
                if not (g.maxx < minx or g.minx > maxx or
                        g.maxy < miny or g.miny > maxy):
                    yield ft

    def bbox_iter(self, bbox):
        """Alias for :meth:`select` taking a ``(minx, miny, maxx, maxy)`` tuple."""
        return self.select(bbox[0], bbox[1], bbox[2], bbox[3])


# --- Writer ---------------------------------------------------------------
cdef bytes _feature_bytes(int geom_type, object xy, object ends, object parts,
                          bytes props):
    cdef vector[double] cxy
    cdef vector[uint32_t] cends
    cdef vector[uint32_t] cparts
    cdef vector[uint8_t] cprops
    cdef Py_ssize_t i
    cdef double[::1] xy_v = np.ascontiguousarray(xy, dtype=np.float64).ravel()
    cdef uint32_t[::1] ends_v
    cdef uint32_t[::1] parts_v
    for i in range(xy_v.shape[0]):
        cxy.push_back(xy_v[i])
    if ends is not None and len(ends):
        ends_v = np.ascontiguousarray(ends, dtype=np.uint32).ravel()
        for i in range(ends_v.shape[0]):
            cends.push_back(ends_v[i])
    if parts is not None and len(parts):
        parts_v = np.ascontiguousarray(parts, dtype=np.uint32).ravel()
        for i in range(parts_v.shape[0]):
            cparts.push_back(parts_v[i])
    for i in range(len(props)):
        cprops.push_back(<uint8_t>props[i])
    cdef string out = build_feature(<uint8_t>geom_type, cxy, cends, cparts, cprops)
    return _bytes_from_ptr(<const uint8_t*>out.data(), out.size())


cdef tuple _xy_envelope(object xy):
    arr = np.asarray(xy, dtype=np.float64).reshape(-1, 2)
    if arr.shape[0] == 0:
        return (0.0, 0.0, 0.0, 0.0)
    return (float(arr[:, 0].min()), float(arr[:, 1].min()),
            float(arr[:, 0].max()), float(arr[:, 1].max()))


class FlatGeobufWriter:
    """Buffered FlatGeobuf writer.

    Features are appended (as size-prefixed FlatBuffers) to a shared *body* file;
    envelopes and byte offsets are recorded. A separate :func:`finalize` pass
    builds the packed Hilbert R-tree and writes the final indexed ``.fgb``.

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
    """

    def __init__(self, path, col_names, col_types, geom_type, name="",
                 crs_wkt="", crs_org="", crs_code=0, node_size=16, lock=None):
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
        self.records = []  # (minx, miny, maxx, maxy, offset, length)
        self._body = open(self.body_path, "ab")

    def add_feature(self, xy, ends=None, parts=None, values=None):
        """Append one feature."""
        props = _encode_properties(list(values), self.col_types) if values else b""
        buf = _feature_bytes(self.geom_type, xy, ends, parts, props)
        env = _xy_envelope(xy)
        if self.lock is not None:
            self.lock.acquire()
        try:
            self._body.seek(0, os.SEEK_END)
            offset = self._body.tell()
            self._body.write(buf)
            self._body.flush()
        finally:
            if self.lock is not None:
                self.lock.release()
        self.records.append((env[0], env[1], env[2], env[3], offset, len(buf)))

    def close(self):
        """Close the body file handle (does not finalize)."""
        if self._body is not None:
            self._body.flush()
            self._body.close()
            self._body = None

    def finalize(self):
        """Finalize a single-writer file (build index + write output)."""
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

    cdef string cname = name.encode("utf-8")
    cdef string cwkt = crs_wkt.encode("utf-8")
    cdef string corg = crs_org.encode("utf-8")

    cdef vector[string] cnames
    cdef vector[uint8_t] ctypes
    for nm in col_names:
        cnames.push_back(nm.encode("utf-8"))
    for ct in col_types:
        ctypes.push_back(<uint8_t>int(ct))

    if n == 0:
        header = build_header(cname, <uint8_t>geom_type, cnames, ctypes, 0,
                              <uint16_t>node_size, 0, 0, 0, 0, 0, corg,
                              <int32_t>crs_code, cwkt)
        with open(path, "wb") as out:
            out.write(_MAGIC)
            out.write(_bytes_from_ptr(<const uint8_t*>header.data(), header.size()))
        if os.path.exists(body_path):
            os.remove(body_path)
        return

    for i in range(n):
        rec = records[i]
        env_all.push_back(rec[0])
        env_all.push_back(rec[1])
        env_all.push_back(rec[2])
        env_all.push_back(rec[3])

    order = hilbert_order(env_all, &extent[0])

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
        running += rec[5]

    index = build_index(env_ordered, new_offsets, &extent[0], <uint16_t>node_size)
    header = build_header(cname, <uint8_t>geom_type, cnames, ctypes,
                          <uint64_t>n, <uint16_t>node_size, 1, extent[0],
                          extent[1], extent[2], extent[3], corg,
                          <int32_t>crs_code, cwkt)

    with open(body_path, "rb") as body, open(path, "wb") as out:
        out.write(_MAGIC)
        out.write(_bytes_from_ptr(<const uint8_t*>header.data(), header.size()))
        out.write(_bytes_from_ptr(<const uint8_t*>index.data(), index.size()))
        for i in range(n):
            rec = ordered_records[i]
            body.seek(rec[4])
            out.write(body.read(rec[5]))

    if os.path.exists(body_path):
        os.remove(body_path)
