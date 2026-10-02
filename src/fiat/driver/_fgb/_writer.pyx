# distutils: language = c++
# cython: language_level=3
"""Cython FlatGeobuf writer backed by the vendored FlatGeobuf C++ sources."""

import os

import numpy as np

from libc.stdint cimport int32_t, uint16_t, uint32_t, uint64_t, uint8_t
from libc.string cimport memcpy
from libcpp.string cimport string
from libcpp.vector cimport vector

from fiat.driver._fgb._bindings cimport (
    build_feature,
    build_header,
    build_index,
    hilbert_order,
)
from fiat.driver._fgb._serialize cimport (
    _bytes_from_ptr,
    _encode_properties,
)
from fiat.driver._fgb._serialize import MAGIC

# FlatGeobuf magic bytes written at the head of every output file.
cdef bytes _MAGIC = MAGIC


# --- Index record ---------------------------------------------------------
# One feature's spatial index entry: its envelope plus the body offset and byte
# length of its serialized bytes. Stored in C++ vectors by the writer (and the
# finalize core) so per-feature bookkeeping avoids Python tuple allocation.
cdef struct _Record:
    double minx
    double miny
    double maxx
    double maxy
    uint64_t offset
    uint64_t length


cdef string _serialize_feature(int geom_type, object xy, object ends,
                               object parts, bytes props, _Record* rec):
    """Serialize one feature and report its envelope + length in a single pass.

    Marshals the numpy geometry arrays + encoded property blob into C++ vectors
    and hands them to ``build_feature``. While copying the interleaved
    coordinates it also accumulates the bounding box, so the writer does not
    need a separate numpy pass over ``xy`` to record the feature envelope.

    Fills ``rec`` with the feature's envelope and serialized ``length`` (the
    caller sets ``rec.offset`` when it appends the bytes) and returns the
    serialized feature bytes as a C++ ``string``.
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
    rec.minx = minx
    rec.miny = miny
    rec.maxx = maxx
    rec.maxy = maxy
    rec.length = out.size()
    return out


cdef class FlatGeobufWriter:
    """Buffered FlatGeobuf writer.

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

    cdef readonly str path
    cdef readonly str body_path
    cdef readonly str name
    cdef readonly list col_names
    cdef readonly list col_types
    cdef readonly int geom_type
    cdef readonly str crs_wkt
    cdef readonly str crs_org
    cdef readonly int crs_code
    cdef readonly int node_size
    cdef object lock
    cdef readonly size_t buffer_size
    cdef object _body
    # Serialized features awaiting flush (appended to directly, no Python bytes).
    cdef string _buffer
    # Pending records with buffer-local offsets, resolved to absolute body
    # offsets on flush; finalized records carry absolute offsets.
    cdef vector[_Record] _pending
    cdef vector[_Record] _records

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
        self._body = open(self.body_path, "ab")

    @property
    def records(self):
        """Index records as a Python list of ``(minx, miny, maxx, maxy,
        offset, length)`` tuples.

        Materialized on access from the internal C++ vector so the records stay
        picklable for the multiprocessing finalize handoff.
        """
        cdef Py_ssize_t i, n = self._records.size()
        cdef list out = [None] * n
        cdef _Record r
        for i in range(n):
            r = self._records[i]
            out[i] = (r.minx, r.miny, r.maxx, r.maxy, r.offset, r.length)
        return out

    def add_feature(self, xy, ends=None, parts=None, values=None):
        """Append one feature to the in-memory buffer.

        The feature is serialized and appended to the in-memory buffer (no lock,
        no file I/O). Its envelope + buffer-local offset + length are recorded so
        the pending records can be resolved to absolute body offsets when the
        buffer is flushed. The buffer is flushed to the shared body file once it
        exceeds ``buffer_size`` bytes.

        Parameters
        ----------
        xy : array-like
            Flat interleaved x, y coordinates.
        ends : array-like, optional
            Cumulative coordinate-pair counts per ring/line.
        parts : array-like, optional
            Cumulative ring counts per polygon (MultiPolygon).
        values : list, optional
            Attribute values aligned with ``col_names``.
        """
        # Encode the attributes, then serialize the whole feature. Serialization
        # also reports the envelope + serialized length (computed in the same
        # pass) via ``rec``.
        cdef bytes props = (
            _encode_properties(list(values), self.col_types) if values else b"")
        cdef _Record rec
        cdef string buf = _serialize_feature(
            self.geom_type, xy, ends, parts, props, &rec)
        # Append the serialized feature to the in-memory buffer, remembering its
        # buffer-local offset so the flush can resolve it to a body offset.
        rec.offset = self._buffer.size()
        self._buffer.append(buf)
        self._pending.push_back(rec)
        # Flush once the buffer grows past the configured threshold.
        if self._buffer.size() >= self.buffer_size:
            self._flush()

    def close(self):
        """Flush buffered features and close the body file handle.

        Returns
        -------
        None
            The writer is left closed.
        """
        if self._body is not None:
            self._flush()
            self._body.flush()
            self._body.close()
            self._body = None

    def finalize(self):
        """Finalize a single-writer file.

        Returns
        -------
        None
            The packed index and final FlatGeobuf file are written to disk.
        """
        # Flush the body, then hand our own records to the finalize core without
        # boxing them into a Python list first.
        self.close()
        _finalize_core(self.path, self.body_path, self.name, self.geom_type,
                       self.col_names, self.col_types, self._records,
                       self.crs_wkt, self.crs_org, self.crs_code, self.node_size)

    cdef _flush(self):
        """Flush the in-memory buffer to the shared body file.

        Takes the optional lock once for the whole block, appends the buffer to
        the body file and resolves every pending feature's buffer-local offset to
        an absolute body offset for the finalize pass.
        """
        if self._pending.empty():
            return
        cdef uint64_t base
        # Serialize appends across processes with the lock (if provided).
        if self.lock is not None:
            self.lock.acquire()
        try:
            self._body.seek(0, os.SEEK_END)
            base = self._body.tell()
            self._body.write(
                _bytes_from_ptr(<const uint8_t*>self._buffer.data(),
                                self._buffer.size()))
            self._body.flush()
        finally:
            if self.lock is not None:
                self.lock.release()
        # Resolve buffer-local offsets to absolute body offsets.
        cdef Py_ssize_t i, n = self._pending.size()
        cdef _Record rec
        for i in range(n):
            rec = self._pending[i]
            rec.offset += base
            self._records.push_back(rec)
        self._buffer.clear()
        self._pending.clear()


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

    Returns
    -------
    None
        The final ``.fgb`` file is written and the body file is removed.
    """
    cdef vector[_Record] recs
    cdef _Record rec
    cdef Py_ssize_t i, n = len(records)
    cdef object t
    for i in range(n):
        t = records[i]
        rec.minx = t[0]
        rec.miny = t[1]
        rec.maxx = t[2]
        rec.maxy = t[3]
        rec.offset = t[4]
        rec.length = t[5]
        recs.push_back(rec)
    _finalize_core(path, body_path, name, geom_type, col_names, col_types,
                   recs, crs_wkt, crs_org, crs_code, node_size)


cdef _finalize_core(str path, str body_path, str name, int geom_type,
                    list col_names, list col_types, vector[_Record]& records,
                    str crs_wkt, str crs_org, int crs_code, int node_size):
    """Build the R-tree and write the final indexed FlatGeobuf file.

    Shared core used by both the public :func:`finalize` (multiprocessing
    parent path) and :meth:`FlatGeobufWriter.finalize` (single-writer path).
    Reads the index records straight from a C++ vector so the single-writer
    path needs no Python-list boxing.
    """
    cdef Py_ssize_t n = records.size()
    cdef vector[double] env_all
    cdef vector[double] env_ordered
    cdef vector[uint64_t] new_offsets
    cdef double extent[4]
    cdef vector[uint64_t] order
    cdef Py_ssize_t i
    cdef unsigned long long idx
    cdef unsigned long long running = 0
    cdef vector[_Record] ordered_records
    cdef _Record rec
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
        env_all.push_back(rec.minx)
        env_all.push_back(rec.miny)
        env_all.push_back(rec.maxx)
        env_all.push_back(rec.maxy)

    # Sort feature indices along the Hilbert curve and get the total extent.
    order = hilbert_order(env_all, &extent[0])

    # Walk features in Hilbert order, computing each one's NEW byte offset in
    # the reordered output and collecting the ordered envelopes for the index.
    ordered_records.resize(n)
    for i in range(n):
        idx = order[i]
        rec = records[idx]
        env_ordered.push_back(rec.minx)
        env_ordered.push_back(rec.miny)
        env_ordered.push_back(rec.maxx)
        env_ordered.push_back(rec.maxy)
        new_offsets.push_back(running)
        ordered_records[i] = rec
        running += rec.length

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
            body.seek(rec.offset)
            out.write(body.read(rec.length))

    # The temporary body file is no longer needed.
    if os.path.exists(body_path):
        os.remove(body_path)
