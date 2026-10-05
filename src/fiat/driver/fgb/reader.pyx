# cython: language_level=3
# distutils: language = c++
"""Cython FlatGeobuf reader backed by the vendored FlatGeobuf C++ sources."""

import numpy as np

from libc.stdint cimport uint32_t, uint64_t, uint8_t
from libc.string cimport memcpy
from libcpp.string cimport string
from libcpp.vector cimport vector

from fiat.driver.fgb.bindings cimport (
    GeometryResult,
    HeaderResult,
    index_size,
    parse_feature,
    parse_header,
    search_index,
)
from fiat.driver.fgb.serialize cimport _decode_properties
from fiat.driver.fgb.serialize import MAGIC
from fiat.driver.vector cimport VectorProfile

# FlatGeobuf magic bytes (8-byte prefix validated on open).
cdef bytes _MAGIC = MAGIC
DEF _MAGIC_LEN = 8


# --- Geometry / Feature ---------------------------------------------------
cdef class Geometry:
    """A 2D geometry as flat coordinate arrays plus ring/part boundaries.

    Instances are created by :func:`make_geometry` or by
    :class:`FlatGeobufReader`.

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
        """Return the geometry envelope.

        Returns
        -------
        tuple
            ``(minx, miny, maxx, maxy)``.
        """
        return (self.minx, self.miny, self.maxx, self.maxy)

    @property
    def coords(self):
        """Return the coordinates reshaped to ``(n, 2)``.

        Returns
        -------
        np.ndarray
            Coordinate array with one x, y pair per row.
        """
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

    Returns
    -------
    Geometry
        Geometry populated with contiguous numpy coordinate arrays.
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
    """A single feature containing geometry and aligned attribute values.

    Attributes
    ----------
    geometry : Geometry
        Feature geometry.
    values : list
        Attribute values aligned with the reader's column order.
    """

    cdef public Geometry geometry
    cdef public list values
    cdef public object _columns  # dict name -> index (shared, may be None)

    def __getitem__(self, key):
        """Return an attribute value by column index or name."""
        return self.get_field(key)

    def geometry_ref(self):
        """Return the feature geometry.

        Returns
        -------
        Geometry
            Feature geometry (OGR-compat alias).
        """
        return self.geometry

    def get_field(self, key):
        """Return an attribute value by column index or name.

        Parameters
        ----------
        key : int | str
            Attribute position or column name.

        Returns
        -------
        object
            Attribute value.
        """
        # Integer index is the hot path; only strings need the name lookup.
        if isinstance(key, str):
            if self._columns is None:
                raise KeyError(key)
            return self.values[self._columns[key]]
        return self.values[key]


# --- Reader ---------------------------------------------------------------
cdef class FlatGeobufReader:
    """Read FlatGeobuf metadata, features and indexed bbox selections.

    Parameters
    ----------
    path : str | path-like
        FlatGeobuf file path.
    crs : str, optional
        A user-provided CRS used only when the layer carries no CRS of its own.
    """

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
    cdef readonly str path
    cdef readonly object crs_override
    cdef public VectorProfile profile
    cdef bint _closed

    def __cinit__(self, path, crs=None):
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

        # Store the source path and build the shared vector profile.
        self.path = str(path)
        self.crs_override = crs
        self._closed = False
        self.profile = VectorProfile(
            crs_wkt=self.crs_wkt,
            crs_org=self.crs_org,
            crs_code=self.crs_code,
            crs_override=crs,
            bounds=self.envelope,
            geom_type=self.geometry_type,
            name=self.name,
            fields=self.col_names,
            dtypes=self.col_types,
            columns=self.columns,
            size=int(self.features_count),
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def __iter__(self):
        """Yield all features in file order."""
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

    def __len__(self):
        """Return the number of features advertised by the header."""
        return int(self.features_count)

    def __reduce__(self):
        """Support pickling by reopening the file by path."""
        return (self.__class__, (self.path, self.crs_override))

    # Internals
    cdef Feature _feature_from(self, GeometryResult* g, string* props):
        """Build a :class:`Feature` from a parsed geometry + raw property blob."""
        cdef Feature ft = Feature.__new__(Feature)
        ft.geometry = _make_geometry(g)
        # Decode the attribute values, or fill with None when there are none.
        if props.size() > 0:
            ft.values = _decode_properties(
                <const uint8_t*>props.data(), props.size(), self.col_types,
            )
        else:
            ft.values = [None] * len(self.col_types)
        # Share the column lookup so features can be indexed by name.
        ft._columns = self.columns
        return ft

    cdef Feature _read_feature_at(self, size_t off):
        """Parse a single feature at byte ``off`` (used by the R-tree search)."""
        cdef GeometryResult g
        cdef string props
        cdef size_t consumed = parse_feature(
            self._ptr + off, self._len - off, g, props,
        )
        if consumed == 0:
            return None
        return self._feature_from(&g, &props)

    # I/O related
    @property
    def closed(self):
        """Return whether the reader has been closed."""
        return self._closed

    def close(self):
        """Close the reader."""
        self._closed = True

    def bbox_iter(self, bbox):
        """Select features intersecting a bounding box tuple.

        Parameters
        ----------
        bbox : tuple
            ``(minx, miny, maxx, maxy)`` selection bounds.

        Returns
        -------
        iterator
            Iterator returned by :meth:`select`.
        """
        return self.select(bbox[0], bbox[1], bbox[2], bbox[3])

    def reduced_iter(self, long si, long ei):
        """Yield features whose 1-based position lies in ``[si, ei]``.

        Parameters
        ----------
        si : int
            First 1-based feature position to yield.
        ei : int
            Last 1-based feature position to yield.

        Yields
        ------
        Feature
            Feature in the requested inclusive range.
        """
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

        Parameters
        ----------
        minx, miny, maxx, maxy : float
            Selection bounds.

        Yields
        ------
        Feature
            Feature whose envelope intersects the selection bounds.
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
