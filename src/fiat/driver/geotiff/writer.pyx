# cython: language_level=3
# distutils: language = c++
"""GeoTIFF / COG writer."""

from pathlib import Path
import os
import struct

import numpy as np
from pyproj.crs import CRS

from libc.stdint cimport uint8_t, uint32_t, uint64_t
from libcpp.string cimport string
from libcpp.vector cimport vector

from fiat.driver.geotiff.bindings cimport (
    CogSpec,
    MetaItem,
    build_cog_header_fixed,
    build_plain_ifd,
    cog_header_size,
    deflate_block,
    downsample_raw,
    downsample_tile,
    encode_tile,
    inflate_block,
)
from fiat.driver.raster cimport GridProfile
from fiat.util import NODATA_VALUE

# Sort out the pread function when on windows
if hasattr(os, "pread"):
    pread = os.pread
else:
    def pread(fd, size, offset):
        pos = os.lseek(fd, 0, os.SEEK_CUR)
        try:
            os.lseek(fd, offset, os.SEEK_SET)
            return os.read(fd, size)
        finally:
            os.lseek(fd, pos, os.SEEK_SET)

if hasattr(os, "pwrite"):
    pwrite = os.pwrite
else:
    def pwrite(fd, data, offset):
        pos = os.lseek(fd, 0, os.SEEK_CUR)
        try:
            os.lseek(fd, offset, os.SEEK_SET)
            return os.write(fd, data)
        finally:
            os.lseek(fd, pos, os.SEEK_SET)

# Expose
__all__ = ["GeotiffWriter", "GeotiffWriterBand", "TileSink", "deflate_tile"]


# netCDF-style dtype code -> (numpy dtype, sample_format, bits_per_sample).
_DTYPE_CODES = {
    "f4": ("float32", 3, 32), "f8": ("float64", 3, 64),
    "i2": ("int16", 2, 16), "i4": ("int32", 2, 32), "i1": ("int8", 2, 8),
    "u1": ("uint8", 1, 8), "u2": ("uint16", 1, 16), "u4": ("uint32", 1, 32),
}

_COMPRESSION_CODES = {
    None: 1, "none": 1, "raw": 1,
    "deflate": 8, "zlib": 8, "gzip": 8,
}

_OPEN_BINARY = getattr(os, "O_BINARY", 0)

# zlib helpers exposed to the TileSink
cpdef bytes deflate_tile(bytes data, int level):
    """DEFLATE-compress a raw tile buffer."""
    cdef const uint8_t* p = <const uint8_t*><const char*>data
    cdef string out = deflate_block(p, len(data), level)
    return <bytes>out


cpdef bytes inflate_tile(bytes data, Py_ssize_t out_bytes):
    """INFLATE a compressed tile into exactly ``out_bytes`` bytes."""
    cdef bytearray buf = bytearray(out_bytes)
    cdef uint8_t[::1] mv = buf
    cdef const uint8_t* src = <const uint8_t*><const char*>data
    cdef size_t n = inflate_block(src, len(data), &mv[0], out_bytes)
    if n != <size_t>out_bytes:
        raise ValueError("DEFLATE tile decompression failed")
    return bytes(buf)


# Pure, typed tile transforms
# Module-level ``cdef`` helpers used by both the serial and parallel write
# paths. The per-tile pixel work (pad, chunky interleave, nodata-aware 2x2
# down-sample) lives in the C++ codec (``encode_tile`` / ``downsample_tile`` /
# ``downsample_raw``); these wrappers just marshal NumPy buffers to it and do
# the file I/O.
cdef bytes _encode_tile(object arr, int spp, int tw, int th, object nodata,
                        object dtype, int sample_format, int bits,
                        bint has_nodata, int compression, int complevel):
    """Encode one tile from ``arr`` (``(spp, h<=th, w<=tw)`` or ``None`` for an
    all-nodata tile) via the C++ codec; returns the (compressed) tile bytes."""
    cdef uint8_t dummy = 0
    cdef const uint8_t[::1] mv
    cdef string out
    cdef double nd = float(nodata) if nodata is not None else 0.0
    if arr is None:
        # A 0x0 source makes the codec fill the whole tile with nodata.
        out = encode_tile(&dummy, 0, 0, tw, th, spp, sample_format, bits, nd,
                          1 if has_nodata else 0, compression, complevel)
        return <bytes>out
    # Interleave the bands (chunky, band axis last) and view as raw bytes.
    chunky = np.ascontiguousarray(np.moveaxis(arr, 0, -1).astype(dtype,
                                                                 copy=False))
    mv = chunky.view(np.uint8).reshape(-1)
    out = encode_tile(&mv[0], <uint32_t>chunky.shape[0],
                      <uint32_t>chunky.shape[1], tw, th, spp, sample_format,
                      bits, nd, 1 if has_nodata else 0, compression, complevel)
    return <bytes>out


cdef bytes _encode_chunky(object chunky, int spp, int tw, int th, object nodata,
                          object dtype, int sample_format, int bits,
                          bint has_nodata, int compression, int complevel):
    """Encode an already-chunky ``(th, tw, spp)`` tile via the C++ codec."""
    cdef const uint8_t[::1] mv
    cdef double nd = float(nodata) if nodata is not None else 0.0
    cdef object cont = np.ascontiguousarray(chunky, dtype=dtype)
    mv = cont.view(np.uint8).reshape(-1)
    cdef string out = encode_tile(&mv[0], <uint32_t>cont.shape[0],
                                  <uint32_t>cont.shape[1], tw, th, spp,
                                  sample_format, bits, nd,
                                  1 if has_nodata else 0, compression, complevel)
    return <bytes>out


cdef bytes _encode_half(object arr, int spp, int tw, int th, object nodata,
                        object dtype, int sample_format, int bits,
                        bint has_nodata, int compression, int complevel):
    """Down-sample ``arr`` (``(spp, h<=th, w<=tw)`` or ``None``) by two and
    return it as a compressed ``(th//2, tw//2)`` half-resolution tile.

    Produced by the worker/serial writer while it still holds the raw tile, so
    the parent can assemble the first overview level without re-inflating the
    full-resolution tiles.
    """
    cdef uint8_t dummy = 0
    cdef const uint8_t[::1] mv
    cdef string out
    cdef double nd = float(nodata) if nodata is not None else 0.0
    if arr is None:
        out = downsample_tile(&dummy, 0, 0, tw // 2, th // 2, spp,
                              sample_format, bits, nd, 1 if has_nodata else 0,
                              compression, complevel)
        return <bytes>out
    chunky = np.ascontiguousarray(np.moveaxis(arr, 0, -1).astype(dtype,
                                                                 copy=False))
    mv = chunky.view(np.uint8).reshape(-1)
    out = downsample_tile(&mv[0], <uint32_t>chunky.shape[0],
                          <uint32_t>chunky.shape[1], tw // 2, th // 2, spp,
                          sample_format, bits, nd, 1 if has_nodata else 0,
                          compression, complevel)
    return <bytes>out


cdef object _downsample_raw(object chunky, int spp, int sample_format, int bits,
                            object nodata, object dtype, bint has_nodata):
    """Down-sample a chunky ``(h, w, spp)`` tile by two into a chunky
    ``(h//2, w//2, spp)`` array (raw, uncompressed) via the C++ codec."""
    cdef const uint8_t[::1] mv
    cdef double nd = float(nodata) if nodata is not None else 0.0
    cdef object cont = np.ascontiguousarray(chunky, dtype=dtype)
    cdef uint32_t out_h = 0, out_w = 0
    mv = cont.view(np.uint8).reshape(-1)
    cdef string raw = downsample_raw(&mv[0], <uint32_t>cont.shape[0],
                                     <uint32_t>cont.shape[1], spp,
                                     sample_format, bits, nd,
                                     1 if has_nodata else 0, out_h, out_w)
    return np.frombuffer(<bytes>raw, dtype=dtype).reshape(out_h, out_w, spp)


cdef object _inflate_to_chunky(bytes blob, int per_tile, int compression,
                               int h, int w, int spp, object dtype):
    """Inflate a compressed blob into a chunky ``(h, w, spp)`` array."""
    if compression == 8:
        raw = inflate_tile(blob, per_tile)
    else:
        raw = blob
    return np.frombuffer(raw, dtype=dtype).reshape(h, w, spp)


cdef bytes _downsample_block_tile(object block, int spp, int tw, int th,
                                  object nodata, object dtype,
                                  int sample_format, int bits, bint has_nodata,
                                  int compression, int complevel):
    """Down-sample a chunky ``(2*th, 2*tw, spp)`` block to a compressed
    ``(th, tw)`` overview tile (the odd-tile-size fallback path)."""
    cdef const uint8_t[::1] mv
    cdef double nd = float(nodata) if nodata is not None else 0.0
    cdef object cont = np.ascontiguousarray(block, dtype=dtype)
    mv = cont.view(np.uint8).reshape(-1)
    cdef string out = downsample_tile(&mv[0], <uint32_t>cont.shape[0],
                                      <uint32_t>cont.shape[1], tw, th, spp,
                                      sample_format, bits, nd,
                                      1 if has_nodata else 0, compression,
                                      complevel)
    return <bytes>out


cdef object _read_tile_chunky(int fd, object off, object bc, int per_tile,
                              int compression, int th, int tw, int spp,
                              object dtype):
    """Read a compressed tile back from ``fd`` as a chunky ``(th, tw, spp)``
    array."""
    blob = pread(fd, bc, off)
    return _inflate_to_chunky(blob, per_tile, compression, th, tw, spp, dtype)


cdef tuple _append_blob(int fd, bytes blob):
    """Append ``blob`` at the end of ``fd`` and return its ``(offset, size)``."""
    cdef object off = os.lseek(fd, 0, os.SEEK_END)
    os.write(fd, blob)
    return (int(off), len(blob))


# The band writer handle, akin to the netcdf writer, also just handy.
cdef class GeotiffWriterBand:
    """A writable band of a :class:`GeotiffWriter` (serial write path)."""

    cdef object _writer
    cdef readonly int index
    cdef readonly str name
    cdef readonly dict attrs

    def __init__(self, writer, int index, str name):
        self._writer = writer
        self.index = index
        self.name = name
        self.attrs = {}

    def set_attr(self, name, value):
        """Attach a metadata attribute to this band (stored in GDAL_METADATA)."""
        self.attrs[name] = str(value)

    def set(self, data, origin):
        """Write ``data`` with its top-left corner at ``origin`` (x, y)."""
        self._writer._set_serial(self.index, np.asarray(data), origin)


# Parallel tile sink, for
cdef class TileSink:
    """Child-process writer that appends compressed tiles to the shared output
    file under a cross-process lock.
    """

    cdef int _fd
    cdef int bits
    cdef int complevel
    cdef int compression
    cdef object dtype
    cdef bint emit_half
    cdef bint has_nodata
    cdef object lock
    cdef int nbx
    cdef object nodata
    cdef int ov_complevel
    cdef int sample_format
    cdef int spp
    cdef int th
    cdef int tw

    def __init__(self, desc, lock):
        self._fd = os.open(desc["path"], os.O_RDWR | _OPEN_BINARY)
        self.bits = desc["bits"]
        self.complevel = desc["complevel"]
        self.compression = desc["compression"]
        self.dtype = np.dtype(desc["dtype"])
        self.emit_half = desc["emit_half"]
        self.has_nodata = desc["has_nodata"]
        self.lock = lock
        self.nbx = desc["nbx"]
        self.nodata = desc["nodata"]
        self.ov_complevel = desc["ov_complevel"]
        self.sample_format = desc["sample_format"]
        self.spp = desc["samples_per_pixel"]
        self.th = desc["tile_height"]
        self.tw = desc["tile_width"]

    # Internals
    cdef tuple _append(self, bytes blob):
        """Append one compressed tile to the shared output under the lock."""
        self.lock.acquire()
        try:
            off = os.lseek(self._fd, 0, os.SEEK_END)
            os.write(self._fd, blob)
        finally:
            self.lock.release()
        return off, len(blob)

    # I/O related
    def close(self):
        """Release the sink's OS handle."""
        try:
            os.close(self._fd)
        except OSError:
            ...

    # Mutating methods
    def write_block(self, origin, data):
        """Compress and append the tile(s) covered by ``data``.

        Parameters
        ----------
        origin : tuple[int, int]
            Tile-aligned ``(col, row)`` of the block's top-left pixel.
        data : np.ndarray
            A ``(bands, height, width)`` array for this block.

        Returns
        -------
        list[tuple]
            One record per tile. For a COG each record is
            ``(tile_id, offset, byte_count, half_blob)`` where ``half_blob`` is
            the compressed half-resolution tile (kept in memory by the parent to
            build the first overview level); for a plain GeoTIFF ``half_blob`` is
            ``None``.
        """
        col0, row0 = int(origin[0]), int(origin[1])
        data = np.asarray(data)
        if data.ndim == 2:
            data = data[np.newaxis, ...]
        _, bh, bw = data.shape
        tw, th = self.tw, self.th
        records = []
        # A block may cover one or more whole tiles; handle each in turn
        for ty in range(0, bh, th):
            for tx in range(0, bw, tw):
                h = min(th, bh - ty)
                w = min(tw, bw - tx)
                sub = data[:, ty:ty + h, tx:tx + w].astype(self.dtype, copy=False)
                blob = _encode_tile(sub, self.spp, tw, th, self.nodata,
                                    self.dtype, self.sample_format, self.bits,
                                    self.has_nodata, self.compression,
                                    self.complevel)
                # When overviews use the fast path, also emit the half-res tile
                # now (we hold the raw data), so the parent never re-inflates the
                # full-res tiles.
                half = None
                if self.emit_half:
                    half = _encode_half(sub, self.spp, tw, th, self.nodata,
                                        self.dtype, self.sample_format,
                                        self.bits, self.has_nodata,
                                        self.compression, self.ov_complevel)
                tid = ((row0 + ty) // th) * self.nbx + ((col0 + tx) // tw)
                off, bc = self._append(blob)
                records.append((tid, off, bc, half))
        return records


# --- Writer -----------------------------------------------------------------
cdef class GeotiffWriter:
    """Hand-rolled GeoTIFF / COG write driver.

    Parameters
    ----------
    file : Path | str
        The output path.
    crs : str, optional
        A user provided spatial reference system if none is set explicitly.
    cog : bool, optional
        Write a Cloud Optimized GeoTIFF (header-first IFDs plus an overview
        pyramid) when True (the default); write a plain tiled GeoTIFF (single
        IFD, no overviews) when False.
    compression : str, optional
        The dataset-wide tile compression codec, by default ``"deflate"``.
    complevel : int, optional
        The DEFLATE level for the full-resolution tiles, by default 5.
    overview_complevel : int, optional
        The DEFLATE level for overview tiles, by default 2 (overviews are
        resampled previews, so a lighter level keeps the finalize fast).
    """

    # State and pathing
    cdef readonly str path
    cdef bint _closed
    cdef bint _cog
    cdef object _crs

    # Grid geometry
    cdef readonly object profile
    cdef int _w
    cdef int _h
    cdef int _tw
    cdef int _th

    # Data model
    cdef int _bits
    cdef int _complevel
    cdef int _compression
    cdef object _compression_arg
    cdef str _dtype
    cdef object _nodata
    cdef bint _has_nodata
    cdef int _ov_complevel
    cdef int _sample_format
    cdef list _variables
    cdef readonly dict variables

    # Georeferencing
    cdef str _citation
    cdef int _epsg
    cdef bint _has_pixel_scale
    cdef bint _has_tiepoint
    cdef int _model_type
    cdef tuple _pixel_scale
    cdef tuple _tiepoint

    # Output file / streaming state
    cdef list _band_data
    cdef object _data_start
    cdef bint _emit_half
    cdef object _fd
    cdef dict _half_blobs
    cdef list _levels
    cdef object _lock
    cdef int _nbx
    cdef bint _parallel
    cdef dict _records

    def __init__(
        self,
        file,
        crs=None,
        cog=True,
        compression="deflate",
        complevel=2,
        overview_complevel=2,
    ):
        # Pathing and type of file
        self.path = Path(file).as_posix()
        self._closed = False
        self._cog = bool(cog)
        self._crs = crs

        # Grid geometry.
        self.profile = None
        self._w = 0
        self._h = 0
        self._tw = 512
        self._th = 512

        # Data model.
        self._bits = 32
        # Compression is a dataset-wide setting (all tiles share the codec).
        self._complevel = int(complevel)
        if compression not in _COMPRESSION_CODES:
            raise ValueError(f"Unsupported compression: {compression!r}")
        self._compression_arg = compression
        self._compression = _COMPRESSION_CODES[compression]
        self._dtype = "float32"
        self._has_nodata = True
        # Overviews are resampled previews, so they use a lighter (faster)
        # compression level by default.
        self._nodata = NODATA_VALUE
        self._ov_complevel = int(overview_complevel)
        self._sample_format = 3
        self._variables = []
        self.variables = {}

        # Georeferencing.
        self._citation = ""
        self._epsg = 0
        self._has_pixel_scale = False
        self._has_tiepoint = False
        self._model_type = 1
        self._pixel_scale = (0.0, 0.0, 0.0)
        self._tiepoint = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

        # Output file / streaming state.
        self._band_data = None
        self._data_start = 0
        self._emit_half = False
        self._fd = None
        self._half_blobs = {}
        self._levels = None
        self._lock = None
        self._nbx = 0
        self._parallel = False
        self._records = {}

    # Dunder methods
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def __getitem__(self, idx):
        return self._variables[idx]

    def __iter__(self):
        return iter(self._variables)

    def __reduce__(self):
        return self.__class__, (
            self.path, self._crs, self._cog,
            self._compression_arg, self._complevel,
            self._ov_complevel,
        )
    # Private methods
    cdef void _begin_output(self) except *:
        """Open the output file and reserve the header region.

        Idempotent: both the serial path (on :meth:`close`) and the parallel
        path (on :meth:`start_parallel`) funnel through here.
        """
        if self._fd is not None:
            return
        if self._w == 0 or self._h == 0:
            raise ValueError("create_spatial_dims must be called before writing")
        self._levels = self._pyramid()
        self._records = {}
        self._half_blobs = {}
        # The fast overview path (workers emit half-res tiles, parent stitches
        # L1 without re-inflating full-res) is only correct for even tile sizes,
        # where 2x2 averaging blocks never straddle a tile edge. Odd tiles fall
        # back to the assemble-then-downsample path in _finalize_cog.
        self._emit_half = self._cog and (self._tw % 2 == 0) and (self._th % 2 == 0)
        if os.environ.get("GEOTIFF_NO_HALF"):
            self._emit_half = False
        cdef int fd = os.open(
            self.path,
            os.O_RDWR | os.O_CREAT | os.O_TRUNC | _OPEN_BINARY,
            0o644,
        )
        self._fd = fd
        cdef uint64_t data_start
        if self._cog:
            # Reserve the (geometry-derived) header; tiles stream in after it.
            data_start = self._header_size()
            os.ftruncate(fd, 0)
            pwrite(fd, b"\x00" * data_start, 0)
            self._data_start = int(data_start)
        else:
            # Plain TIFF: an 8-byte header placeholder, patched on close.
            pwrite(fd, b"\x00" * 8, 0)
            self._data_start = 8
        os.lseek(fd, self._data_start, os.SEEK_SET)

    cdef void _emit_tile(self, int fd, int tid, object sub, int spp) except *:
        """Encode + append one full-res tile (and, for a COG, keep its half-res
        tile in memory for the first overview level)."""
        blob = _encode_tile(sub, spp, self._tw, self._th, self._nodata,
                            self._dtype, self._sample_format, self._bits,
                            self._has_nodata, self._compression, self._complevel)
        self._records[tid] = _append_blob(fd, blob)
        if self._emit_half:
            self._half_blobs[tid] = _encode_half(
                sub, spp, self._tw, self._th, self._nodata, self._dtype,
                self._sample_format, self._bits, self._has_nodata,
                self._compression, self._ov_complevel)

    cdef void _fill_spec(self, CogSpec* spec) except *:
        """Populate the C++ :cpp:class:`CogSpec` from the writer's typed state.

        Used both to size the reserved COG header and to build the final header,
        so the two always agree. All per-band metadata is handed to the C++ codec
        as :cpp:class:`MetaItem` entries; the codec builds the GDAL_METADATA XML
        and the GDAL_NODATA ASCII value.
        """
        cdef int i
        cdef MetaItem mi
        cdef GeotiffWriterBand band
        spec.width = self._w
        spec.height = self._h
        spec.tile_width = self._tw
        spec.tile_height = self._th
        spec.samples_per_pixel = self.size
        spec.bits_per_sample = self._bits
        spec.sample_format = self._sample_format
        spec.compression = self._compression
        spec.predictor = 1
        spec.has_nodata = 1 if self._has_nodata else 0
        spec.nodata = float(self._nodata) if self._has_nodata else 0.0
        spec.has_pixel_scale = 1 if self._has_pixel_scale else 0
        spec.pixel_scale[0] = self._pixel_scale[0]
        spec.pixel_scale[1] = self._pixel_scale[1]
        spec.pixel_scale[2] = self._pixel_scale[2]
        spec.has_tiepoint = 1 if self._has_tiepoint else 0
        for i in range(6):
            spec.tiepoint[i] = self._tiepoint[i]
        spec.model_type = self._model_type
        spec.raster_type = 1
        spec.epsg = self._epsg
        spec.crs_citation = self._citation.encode("utf-8")
        # Per-band metadata: the band name round-trips as its DESCRIPTION item,
        # followed by any user attributes (mirrors GDAL's GDAL_METADATA).
        for band in self._variables:
            mi.name = b"DESCRIPTION"
            mi.value = band.name.encode("utf-8")
            mi.sample = band.index
            spec.meta_items.push_back(mi)
            for key, value in band.attrs.items():
                mi.name = str(key).encode("utf-8")
                mi.value = str(value).encode("utf-8")
                mi.sample = band.index
                spec.meta_items.push_back(mi)

    cdef uint64_t _header_size(self) except *:
        """Deterministic size of the reserved COG header region (bytes)."""
        cdef CogSpec spec
        self._fill_spec(&spec)
        cdef vector[uint32_t] lw, lh
        for (w, h) in self._levels:
            lw.push_back(<uint32_t>w)
            lh.push_back(<uint32_t>h)
        return cog_header_size(spec, lw, lh)

    cdef object _pyramid(self):
        """Return the ``(width, height)`` of every level (level 0 = full res)."""
        levels = [(self._w, self._h)]
        cdef int w = self._w
        cdef int h = self._h
        if self._cog:
            while w > self._tw or h > self._th:
                w = (w + 1) // 2
                h = (h + 1) // 2
                levels.append((w, h))
        return levels

    cpdef _set_serial(self, int index, object data, object origin):
        """Buffer a window of one band for the serial write path.

        Full-band writes are kept by reference (no copy); partial windows fall
        back to a lazily-allocated per-band buffer. The whole raster is never
        allocated in one block -- tiles are assembled and streamed on
        :meth:`close`.
        """
        if self._band_data is None:
            self._band_data = [None] * self.size
        data = np.asarray(data)
        cdef int x0 = int(origin[0])
        cdef int y0 = int(origin[1])
        cdef int h = <int>data.shape[0]
        cdef int w = <int>data.shape[1]
        if (self._band_data[index] is None and x0 == 0 and y0 == 0
                and h == self._h and w == self._w):
            self._band_data[index] = data
            return
        buf = self._band_data[index]
        if buf is None:
            buf = np.full((self._h, self._w), self._nodata, dtype=self._dtype)
            self._band_data[index] = buf
        buf[y0:y0 + h, x0:x0 + w] = data

    cdef void _write_full_res_from_bands(self) except *:
        """Stream the full-resolution tiles from the buffered band data."""
        cdef int fd = <int>self._fd
        cdef int spp = self.size
        cdef int nbx = (self._w + self._tw - 1) // self._tw
        cdef int nby = (self._h + self._th - 1) // self._th
        cdef int ty, tx, r0, c0, bh, bw, b
        bands = self._band_data if self._band_data is not None else [None] * spp
        for ty in range(nby):
            for tx in range(nbx):
                r0 = ty * self._th
                c0 = tx * self._tw
                bh = min(self._th, self._h - r0)
                bw = min(self._tw, self._w - c0)
                block = np.empty((spp, bh, bw), dtype=self._dtype)
                for b in range(spp):
                    bd = bands[b]
                    if bd is None:
                        block[b, :, :] = self._nodata
                    else:
                        block[b, :, :] = bd[r0:r0 + bh, c0:c0 + bw]
                self._emit_tile(fd, ty * nbx + tx, block, spp)
        self._band_data = None

    # Properties
    @property
    def closed(self):
        """Return whether the dataset has been closed."""
        return self._closed

    @property
    def cog(self):
        """Return whether the writer emits a Cloud Optimized GeoTIFF."""
        return self._cog

    @property
    def names(self):
        """Return the band names."""
        return list(self.variables.keys())

    @property
    def size(self):
        """Return the number of bands."""
        return len(self.variables)

    # I/O methods
    def close(self):
        """Finalise and write the GeoTIFF, releasing any parallel resources."""
        if self._closed:
            return
        try:
            if self._band_data is not None:
                # Buffered serial writes (band.set): open now and stream them.
                self._begin_output()
                self._write_full_res_from_bands()
            elif self._fd is None:
                # Nothing was written: emit an all-nodata grid.
                self._begin_output()
            # Otherwise tiles were already streamed (write_window / workers).
            if self._cog:
                self._finalize_cog()
            else:
                self._finalize_plain()
        finally:
            if self._fd is not None:
                try:
                    os.close(<int>self._fd)
                except OSError:
                    ...
                self._fd = None
            self._closed = True

    def flush(self):
        """No-op; the file is finalised atomically on close."""

    def write_window(self, origin, data):
        """Stream a multi-band window straight to the output file.

        This is the streaming, bounded-memory write path (the serial counterpart
        of a worker's :meth:`TileSink.write_block`): the window's tiles are
        encoded and appended to the file immediately, so the whole raster is
        never buffered. ``data`` is shaped ``(bands, h, w)`` (or ``(h, w)`` for a
        single band); ``origin`` is the ``(x, y)`` top-left pixel and should be
        tile-aligned for clean streaming.

        Parameters
        ----------
        origin : tuple[int, int]
            The ``(x, y)`` top-left pixel of the window.
        data : np.ndarray
            A ``(bands, h, w)`` (or ``(h, w)``) array for this window.
        """
        self._begin_output()
        data = np.asarray(data)
        if data.ndim == 2:
            data = data[np.newaxis, ...]
        cdef int fd = <int>self._fd
        cdef int nb = <int>data.shape[0]
        cdef int h = <int>data.shape[1]
        cdef int w = <int>data.shape[2]
        cdef int x0 = int(origin[0])
        cdef int y0 = int(origin[1])
        cdef int tw = self._tw
        cdef int th = self._th
        cdef int nbx = (self._w + tw - 1) // tw
        cdef int ty, tx, sh, sw
        for ty in range(0, h, th):
            for tx in range(0, w, tw):
                sh = min(th, h - ty)
                sw = min(tw, w - tx)
                sub = data[:, ty:ty + sh, tx:tx + sw]
                self._emit_tile(fd, ((y0 + ty) // th) * nbx + ((x0 + tx) // tw),
                                sub, nb)

    # Mutating methods
    def create_spatial_dims(self, lats, lons):
        """Create the spatial grid from latitude/longitude cell centres."""
        # Build the shared profile and record the grid shape
        lats = np.asarray(lats)
        lons = np.asarray(lons)
        self.profile = GridProfile(xvals=lons, yvals=lats, crs_wkt=self._crs)
        self._h = int(len(lats))
        self._w = int(len(lons))
        # Derive the GeoTIFF pixel scale + tiepoint from the geotransform
        t = self.profile.transform
        self._pixel_scale = (abs(t[1]), abs(t[5]), 0.0)
        self._has_pixel_scale = True
        self._tiepoint = (0.0, 0.0, 0.0, t[0], t[3], 0.0)
        self._has_tiepoint = True

    def create_spatial_variable(self, var, dtype="f4", nodata=NODATA_VALUE):
        """Register an output band."""
        # Resolve the data type (all bands must share it for chunky storage)
        if dtype not in _DTYPE_CODES:
            raise ValueError(f"Unsupported dtype code: {dtype!r}")
        np_dtype, sf, bits = _DTYPE_CODES[dtype]
        if self._variables and np_dtype != self._dtype:
            raise ValueError("All bands must share the same dtype")
        self._dtype = np_dtype
        self._sample_format = sf
        self._bits = bits
        self._nodata = nodata
        self._has_nodata = nodata is not None

        # Register the band and return it
        band = GeotiffWriterBand(self, len(self._variables), var)
        self.variables[var] = band
        self._variables.append(band)
        return band

    def set_block_size(self, tile_width, tile_height=None):
        """Set the tile size; also the parallel write granularity."""
        self._tw = int(tile_width)
        self._th = int(tile_height if tile_height is not None else tile_width)

    def set_spatial_ref(self, crs):
        """Set the coordinate reference system."""
        if not isinstance(crs, CRS):
            crs = CRS.from_user_input(crs)
        # Prefer the EPSG code; keep the WKT as a citation fallback
        epsg = crs.to_epsg()
        self._epsg = int(epsg) if epsg else 0
        self._model_type = 2 if crs.is_geographic else 1
        self._citation = crs.name if self._epsg else crs.to_wkt()
        if self.profile is not None:
            self.profile.crs_wkt = crs.to_wkt()

    # Worker methods
    cpdef collect_records(self, object results):
        """Register the per-tile records workers wrote.

        Each record is ``(tile_id, offset, byte_count, half_blob)`` where
        ``half_blob`` is the compressed half-resolution tile (kept in memory to
        build the first overview level) or ``None`` for a plain GeoTIFF.
        ``results`` may be an iterable of such tuples or of lists of them (as
        returned by the worker pool).
        """
        for item in results:
            if item is None:
                continue
            if isinstance(item, tuple) and not isinstance(item[0], (list, tuple)):
                recs = [item]
            else:
                recs = item
            for rec in recs:
                tid = int(rec[0])
                self._records[tid] = (int(rec[1]), int(rec[2]))
                if len(rec) > 3 and rec[3] is not None:
                    self._half_blobs[tid] = rec[3]

    def sink_descriptor(self):
        """Return a picklable descriptor workers use to build a :class:`TileSink`."""
        if not self._parallel:
            raise ValueError("start_parallel must be called first")
        return {
            "path": self.path,
            "tile_width": self._tw,
            "tile_height": self._th,
            "nbx": self._nbx,
            "samples_per_pixel": self.size,
            "nodata": self._nodata,
            "complevel": self._complevel,
            "ov_complevel": self._ov_complevel,
            "emit_half": self._emit_half,
            "compression": self._compression,
            "sample_format": self._sample_format,
            "bits": self._bits,
            "has_nodata": self._has_nodata,
            "dtype": self._dtype,
        }

    def start_parallel(self, ctx):
        """Set up the shared output file and lock for child-process writes.

        Returns the cross-process lock to pass to workers (alongside
        :meth:`sink_descriptor`).
        """
        self._begin_output()
        self._parallel = True
        self._lock = ctx.Lock()
        self._nbx = (self._w + self._tw - 1) // self._tw
        return self._lock

    # Finalization
    cdef void _fill_missing_full_res(self) except *:
        """Append nodata tiles for any full-resolution tile never written."""
        cdef int fd = <int>self._fd
        cdef int nbx = (self._w + self._tw - 1) // self._tw
        cdef int nby = (self._h + self._th - 1) // self._th
        cdef int tid
        for tid in range(nbx * nby):
            if tid not in self._records:
                blob = _encode_tile(None, self.size, self._tw, self._th,
                                    self._nodata, self._dtype,
                                    self._sample_format, self._bits,
                                    self._has_nodata, self._compression,
                                    self._complevel)
                self._records[tid] = _append_blob(fd, blob)
            if self._emit_half and tid not in self._half_blobs:
                self._half_blobs[tid] = _encode_half(
                    None, self.size, self._tw, self._th, self._nodata,
                    self._dtype, self._sample_format, self._bits,
                    self._has_nodata, self._compression, self._ov_complevel)

    cdef dict _build_overview_l1(self, int fd):
        """Build the first overview level from the workers' half-res tiles.

        Each level-1 tile stitches the 2x2 block of half-resolution tiles the
        writers produced while they held the raw data, so no full-resolution
        tile is ever re-inflated.
        """
        cdef int tw = self._tw
        cdef int th = self._th
        cdef int hw = tw // 2
        cdef int hh = th // 2
        cdef int spp = self.size
        cdef int half_per_tile = hh * hw * spp * (self._bits // 8)
        cdef int full_nbx = (self._w + tw - 1) // tw
        cdef int full_nby = (self._h + th - 1) // th
        cdef int cw = self._levels[1][0]
        cdef int ch = self._levels[1][1]
        cdef int child_nbx = (cw + tw - 1) // tw
        cdef int child_nby = (ch + th - 1) // th
        cdef dict child = {}
        cdef int cty, ctx, dy, dx, ftx, fty, fid
        for cty in range(child_nby):
            for ctx in range(child_nbx):
                # Place the four half-res quadrants into a full-size child tile
                tile = np.full((th, tw, spp), self._nodata, dtype=self._dtype)
                for dy in range(2):
                    for dx in range(2):
                        ftx = 2 * ctx + dx
                        fty = 2 * cty + dy
                        if ftx < full_nbx and fty < full_nby:
                            fid = fty * full_nbx + ftx
                            blob = self._half_blobs.get(fid)
                            if blob is not None:
                                tile[dy * hh:(dy + 1) * hh,
                                     dx * hw:(dx + 1) * hw, :] = \
                                    _inflate_to_chunky(blob, half_per_tile,
                                                       self._compression, hh, hw,
                                                       spp, self._dtype)
                enc = _encode_chunky(tile, spp, tw, th, self._nodata,
                                     self._dtype, self._sample_format,
                                     self._bits, self._has_nodata,
                                     self._compression, self._ov_complevel)
                child[cty * child_nbx + ctx] = _append_blob(fd, enc)
        return child

    cdef dict _build_overview_level(self, int fd, dict parent, int pw, int ph,
                                    int cw, int ch):
        """Build a deeper overview level from its parent.

        Each parent tile is down-sampled (C++, nodata-aware) into a half-size
        quadrant that is placed directly into the full-size child tile -- so only
        a single tile-sized buffer is allocated per child (no 2x larger scratch
        block), and only the small parent levels are read back.
        """
        cdef int tw = self._tw
        cdef int th = self._th
        cdef int hw = tw // 2
        cdef int hh = th // 2
        cdef int spp = self.size
        cdef int per_tile = th * tw * spp * (self._bits // 8)
        cdef int parent_nbx = (pw + tw - 1) // tw
        cdef int parent_nby = (ph + th - 1) // th
        cdef int child_nbx = (cw + tw - 1) // tw
        cdef int child_nby = (ch + th - 1) // th
        cdef dict child = {}
        cdef int cty, ctx, dy, dx, ptx, pty, ptid
        for cty in range(child_nby):
            for ctx in range(child_nbx):
                tile = np.full((th, tw, spp), self._nodata, dtype=self._dtype)
                for dy in range(2):
                    for dx in range(2):
                        ptx = 2 * ctx + dx
                        pty = 2 * cty + dy
                        if ptx < parent_nbx and pty < parent_nby:
                            ptid = pty * parent_nbx + ptx
                            rec = parent.get(ptid)
                            if rec is not None:
                                ptile = _read_tile_chunky(
                                    fd, rec[0], rec[1], per_tile,
                                    self._compression, th, tw, spp, self._dtype)
                                quad = _downsample_raw(
                                    ptile, spp, self._sample_format, self._bits,
                                    self._nodata, self._dtype, self._has_nodata)
                                tile[dy * hh:dy * hh + quad.shape[0],
                                     dx * hw:dx * hw + quad.shape[1], :] = quad
                enc = _encode_chunky(tile, spp, tw, th, self._nodata,
                                     self._dtype, self._sample_format,
                                     self._bits, self._has_nodata,
                                     self._compression, self._ov_complevel)
                child[cty * child_nbx + ctx] = _append_blob(fd, enc)
        return child

    cdef dict _build_overview_slow(self, int fd, dict parent, int pw, int ph,
                                   int cw, int ch):
        """Build an overview level by assembling the 2x2 block of parent tiles
        and down-sampling the whole block (fallback for odd tile sizes, where
        per-tile down-sampling would be wrong at tile edges)."""
        cdef int tw = self._tw
        cdef int th = self._th
        cdef int spp = self.size
        cdef int per_tile = th * tw * spp * (self._bits // 8)
        cdef int parent_nbx = (pw + tw - 1) // tw
        cdef int parent_nby = (ph + th - 1) // th
        cdef int child_nbx = (cw + tw - 1) // tw
        cdef int child_nby = (ch + th - 1) // th
        cdef dict child = {}
        cdef int cty, ctx, dy, dx, ptx, pty, ptid
        for cty in range(child_nby):
            for ctx in range(child_nbx):
                block = np.full(
                    (2 * th, 2 * tw, spp), self._nodata,
                    dtype=self._dtype,
                )
                for dy in range(2):
                    for dx in range(2):
                        ptx = 2 * ctx + dx
                        pty = 2 * cty + dy
                        if ptx < parent_nbx and pty < parent_nby:
                            ptid = pty * parent_nbx + ptx
                            rec = parent.get(ptid)
                            if rec is not None:
                                block[dy * th:(dy + 1) * th,
                                      dx * tw:(dx + 1) * tw, :] = \
                                    _read_tile_chunky(fd, rec[0], rec[1],
                                                      per_tile, self._compression,
                                                      th, tw, spp, self._dtype)
                enc = _downsample_block_tile(block, spp, tw, th, self._nodata,
                                             self._dtype, self._sample_format,
                                             self._bits, self._has_nodata,
                                             self._compression,
                                             self._ov_complevel)
                child[cty * child_nbx + ctx] = _append_blob(fd, enc)
        return child

    cdef void _finalize_cog(self) except *:
        """Build the overview pyramid and patch in the header-first COG layout."""
        cdef int fd = <int>self._fd
        cdef int tw = self._tw
        cdef int th = self._th
        cdef int L, pw, ph, cw, ch, nbx, nby, tid
        self._fill_missing_full_res()

        # L1 from the workers' half-res tiles (no full-res re-inflation); deeper
        # levels from the (small) level below, a quadrant at a time.
        level_records = [self._records]
        for L in range(1, len(self._levels)):
            pw, ph = self._levels[L - 1]
            cw, ch = self._levels[L]
            if L == 1 and self._emit_half:
                # Fast path: stitch L1 from the workers' half-res tiles.
                level_records.append(self._build_overview_l1(fd))
            elif self._emit_half:
                # Fast path: deeper levels, a quadrant at a time (small buffers).
                level_records.append(
                    self._build_overview_level(fd, level_records[L - 1],
                                               pw, ph, cw, ch))
            else:
                # Odd tile size: assemble the 2x2 block then down-sample (correct
                # across tile edges).
                level_records.append(
                    self._build_overview_slow(fd, level_records[L - 1],
                                              pw, ph, cw, ch))
        self._half_blobs = {}

        # Collect per-level offsets + byte counts in tile order for the codec.
        cdef CogSpec spec
        self._fill_spec(&spec)
        cdef vector[uint32_t] lw, lh
        cdef vector[vector[uint64_t]] offs_v, bcs_v
        cdef vector[uint64_t] inner_o, inner_b
        for L in range(len(self._levels)):
            cw, ch = self._levels[L]
            lw.push_back(<uint32_t>cw)
            lh.push_back(<uint32_t>ch)
            nbx = (cw + tw - 1) // tw
            nby = (ch + th - 1) // th
            inner_o.clear()
            inner_b.clear()
            recs = level_records[L]
            for tid in range(nbx * nby):
                rec = recs[tid]
                inner_o.push_back(<uint64_t>rec[0])
                inner_b.push_back(<uint64_t>rec[1])
            offs_v.push_back(inner_o)
            bcs_v.push_back(inner_b)

        cdef string header = build_cog_header_fixed(spec, lw, lh, offs_v, bcs_v)
        pwrite(fd, <bytes>header, 0)

    cdef void _finalize_plain(self) except *:
        """Append the trailing single IFD and patch the TIFF header pointer."""
        cdef int fd = <int>self._fd
        cdef int tw = self._tw
        cdef int th = self._th
        cdef int nbx = (self._w + tw - 1) // tw
        cdef int nby = (self._h + th - 1) // th
        cdef int tid
        self._fill_missing_full_res()

        cdef CogSpec spec
        self._fill_spec(&spec)
        cdef vector[uint64_t] offs, bcs
        for tid in range(nbx * nby):
            rec = self._records[tid]
            offs.push_back(<uint64_t>rec[0])
            bcs.push_back(<uint64_t>rec[1])

        # The IFD block goes at the end of the tile data; the 8-byte header then
        # points to it.
        cdef object ifd_start = os.lseek(fd, 0, os.SEEK_END)
        cdef string block = build_plain_ifd(
            spec, self._w, self._h, offs, bcs, <uint64_t>ifd_start,
        )
        os.write(fd, <bytes>block)
        pwrite(fd, b"II" + struct.pack("<HI", 42, int(ifd_start)), 0)
