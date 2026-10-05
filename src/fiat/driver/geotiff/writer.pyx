# cython: language_level=3
# distutils: language = c++
"""Hand-rolled GeoTIFF / COG write driver.

Writes tiled, DEFLATE-compressed, strict Cloud Optimized GeoTIFFs (header-first
IFDs plus an overview pyramid) via the C++ codec in ``tiff_c.cpp``. The public
surface mirrors :class:`fiat.driver.netcdf.NetcdfWriter` so it is a drop-in in
the grid model, and it additionally supports **direct writes from child
processes** to a single shared file.

Parallel model: workers compress their tiles and append them to a scratch file
under a cross-process lock, recording ``(offset, byte_count)`` per tile in a
shared-memory index. The parent reconstructs the full-resolution raster, builds
the overview pyramid and emits the final COG in :meth:`GeotiffWriter.close`.
"""

import os

import numpy as np
from pyproj.crs import CRS

from libc.stdint cimport uint8_t, uint32_t, uint64_t
from libcpp.string cimport string
from libcpp.vector cimport vector

from fiat.driver.geotiff.bindings cimport (
    CogSpec,
    build_cog_header,
    deflate_block,
    inflate_block,
)
from fiat.driver.raster cimport GridProfile

from fiat.util import NODATA_VALUE

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


# --- zlib helpers exposed to the pure-Python TileSink ----------------------
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


cdef object _build_cog_header_py(dict spec_d, list level_w, list level_h,
                                 list level_bc):
    """Thin wrapper around C++ ``build_cog_header`` using Python containers."""
    cdef CogSpec spec
    spec.width = spec_d["width"]
    spec.height = spec_d["height"]
    spec.tile_width = spec_d["tile_width"]
    spec.tile_height = spec_d["tile_height"]
    spec.samples_per_pixel = spec_d["samples_per_pixel"]
    spec.bits_per_sample = spec_d["bits_per_sample"]
    spec.sample_format = spec_d["sample_format"]
    spec.compression = spec_d["compression"]
    spec.predictor = spec_d["predictor"]
    spec.has_nodata = 1 if spec_d["has_nodata"] else 0
    spec.nodata = spec_d["nodata"]
    spec.has_pixel_scale = 1 if spec_d["has_pixel_scale"] else 0
    spec.pixel_scale[0] = spec_d["pixel_scale"][0]
    spec.pixel_scale[1] = spec_d["pixel_scale"][1]
    spec.pixel_scale[2] = spec_d["pixel_scale"][2]
    spec.has_tiepoint = 1 if spec_d["has_tiepoint"] else 0
    for i in range(6):
        spec.tiepoint[i] = spec_d["tiepoint"][i]
    spec.model_type = spec_d["model_type"]
    spec.raster_type = spec_d["raster_type"]
    spec.epsg = spec_d["epsg"]
    spec.crs_citation = spec_d["crs_citation"].encode("utf-8")
    spec.gdal_nodata_ascii = spec_d["gdal_nodata_ascii"].encode("utf-8")
    spec.gdal_metadata_xml = spec_d["gdal_metadata_xml"].encode("utf-8")

    cdef vector[uint32_t] lw, lh
    cdef vector[vector[uint64_t]] bcs
    cdef vector[uint64_t] inner
    cdef Py_ssize_t i2
    for v in level_w:
        lw.push_back(<uint32_t>v)
    for v in level_h:
        lh.push_back(<uint32_t>v)
    for lvl in level_bc:
        inner.clear()
        for v in lvl:
            inner.push_back(<uint64_t>v)
        bcs.push_back(inner)

    cdef uint64_t data_start = 0
    cdef vector[uint64_t] toff
    cdef string header = build_cog_header(spec, lw, lh, bcs, data_start, toff)
    cdef list offsets = [int(toff[i2]) for i2 in range(toff.size())]
    return <bytes>header, int(data_start), offsets


# --- Band -------------------------------------------------------------------
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


# --- Parallel tile sink -----------------------------------------------------
cdef class TileSink:
    """Child-process writer that appends compressed tiles to a shared scratch
    file under a cross-process lock.

    Constructed inside each worker from the picklable descriptor produced by
    :meth:`GeotiffWriter.sink_descriptor` and a shared lock. Each
    :meth:`write_block` call returns the ``(tile_id, offset, byte_count)``
    records of the tiles it wrote; the parent collects these via the pool
    results to rebuild the tile index (no shared memory required).
    """

    cdef object lock
    cdef int tw
    cdef int th
    cdef int nbx
    cdef int spp
    cdef object nodata
    cdef int complevel
    cdef int compression
    cdef object dtype
    cdef int _fd

    def __init__(self, desc, lock):
        self.lock = lock
        self.tw = desc["tile_width"]
        self.th = desc["tile_height"]
        self.nbx = desc["nbx"]
        self.spp = desc["samples_per_pixel"]
        self.nodata = desc["nodata"]
        self.complevel = desc["complevel"]
        self.compression = desc["compression"]
        self.dtype = np.dtype(desc["dtype"])
        self._fd = os.open(desc["scratch"], os.O_RDWR)

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
        list[tuple[int, int, int]]
            ``(tile_id, offset, byte_count)`` for each written tile.
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
                # Pad the (possibly partial) tile and interleave the bands
                h = min(th, bh - ty)
                w = min(tw, bw - tx)
                tile = np.full((th, tw, self.spp), self.nodata, dtype=self.dtype)
                sub = data[:, ty:ty + h, tx:tx + w].astype(self.dtype, copy=False)
                tile[:h, :w, :] = np.moveaxis(sub, 0, -1)
                # Compress and append it, recording its global tile id + location
                raw = np.ascontiguousarray(tile).tobytes()
                if self.compression == 8:
                    blob = deflate_tile(raw, self.complevel)
                else:
                    blob = raw
                tid = ((row0 + ty) // th) * self.nbx + ((col0 + tx) // tw)
                records.append((tid, *self._append(blob)))
        return records

    cdef tuple _append(self, bytes blob):
        """Append one compressed tile to the shared scratch under the lock."""
        self.lock.acquire()
        try:
            off = os.lseek(self._fd, 0, os.SEEK_END)
            os.write(self._fd, blob)
        finally:
            self.lock.release()
        return off, len(blob)

    def close(self):
        """Release the sink's OS handle."""
        try:
            os.close(self._fd)
        except OSError:
            ...


# --- COG build helpers ------------------------------------------------------
# Pure, fully typed transformations used by the writer's finalize pass. They are
# module-level functions (not methods) because they depend only on their inputs,
# mirroring the ``deflate_tile`` / ``build_cog_header`` helpers above.
cdef bytes _tile_bytes(object arr, int tx, int ty, int tw, int th,
                       object nodata, object dtype):
    """Cut tile ``(tx, ty)`` from ``arr`` as padded, chunky, raw bytes."""
    cdef int spp = arr.shape[0]
    # Pad the (possibly edge-clipped) tile to full size with nodata
    tile = np.full((th, tw, spp), nodata, dtype=dtype)
    cdef int r0 = ty * th
    cdef int c0 = tx * tw
    cdef int h = min(th, <int>arr.shape[1] - r0)
    cdef int w = min(tw, <int>arr.shape[2] - c0)
    # Interleave the bands (band axis last) for chunky tile storage
    tile[:h, :w, :] = np.moveaxis(arr[:, r0:r0 + h, c0:c0 + w], 0, -1)
    return np.ascontiguousarray(tile).tobytes()


cdef object _downsample(object arr, int sample_format, bint has_nodata,
                        object nodata, object dtype):
    """Halve the resolution (average, nodata-aware for float; decimate else)."""
    cdef int spp = arr.shape[0]
    cdef int h = arr.shape[1]
    cdef int w = arr.shape[2]
    cdef int h2 = (h + 1) // 2
    cdef int w2 = (w + 1) // 2
    cdef int pad_h, pad_w
    if sample_format == 3:
        # Float: average 2x2 blocks, ignoring nodata (mapped to NaN)
        a = arr.astype(np.float64)
        if has_nodata:
            a[a == nodata] = np.nan
        # Pad odd dimensions with NaN so they drop out of the mean
        pad_h, pad_w = h2 * 2 - h, w2 * 2 - w
        if pad_h or pad_w:
            a = np.pad(a, ((0, 0), (0, pad_h), (0, pad_w)),
                       constant_values=np.nan)
        a = a.reshape(spp, h2, 2, w2, 2)
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            m = np.nanmean(a, axis=(2, 4))
        if has_nodata:
            m[np.isnan(m)] = nodata
        else:
            m[np.isnan(m)] = 0
        return m.astype(dtype)
    return np.ascontiguousarray(arr[:, ::2, ::2])


cdef list _compress_level(object arr, int tw, int th, object nodata,
                          object dtype, int compression, int complevel):
    """Tile and DEFLATE a whole resolution level into a list of blobs."""
    cdef int nbx = (<int>arr.shape[2] + tw - 1) // tw
    cdef int nby = (<int>arr.shape[1] + th - 1) // th
    cdef list blobs = []
    cdef int tx, ty
    for ty in range(nby):
        for tx in range(nbx):
            raw = _tile_bytes(arr, tx, ty, tw, th, nodata, dtype)
            if compression == 8:
                blobs.append(deflate_tile(raw, complevel))
            else:
                blobs.append(raw)
    return blobs


cdef str _gdal_metadata_xml(list variables):
    """Build the GDAL_METADATA XML carrying per-band names and attributes."""
    cdef list parts = ["<GDALMetadata>"]
    cdef GeotiffWriterBand band
    for band in variables:
        # The band name round-trips as its DESCRIPTION item
        parts.append(
            f'<Item name="DESCRIPTION" sample="{band.index}" '
            f'role="description">{band.name}</Item>'
        )
        for key, value in band.attrs.items():
            parts.append(
                f'<Item name="{key}" sample="{band.index}">{value}</Item>'
            )
    parts.append("</GDALMetadata>")
    return "".join(parts)


cdef tuple _reconstruct_full(dict records, int scratch_fd, int spp, int h,
                             int w, int th, int tw, int bits, int compression,
                             object nodata, object dtype, int nbx):
    """Rebuild the full-resolution raster from the scratch tiles.

    Also returns the compressed level-0 blobs keyed by tile id so the COG writer
    can reuse them verbatim instead of recompressing.
    """
    # Untouched tiles stay nodata
    full = np.full((spp, h, w), nodata, dtype=dtype)
    cdef dict reuse = {}
    cdef int per_tile = th * tw * spp * (bits // 8)
    cdef int tid, off, bc, ty, tx, r0, c0, bh, bw
    for tid, rec in records.items():
        off = rec[0]
        bc = rec[1]
        if bc == 0:
            continue
        # Read the compressed tile back from scratch and keep it for reuse
        blob = os.pread(scratch_fd, bc, off)
        reuse[tid] = blob
        if compression == 8:
            raw = inflate_tile(blob, per_tile)
        else:
            raw = blob
        # De-interleave the chunky tile and place it in the raster
        tile = np.frombuffer(raw, dtype=dtype).reshape(th, tw, spp)
        ty, tx = tid // nbx, tid % nbx
        r0, c0 = ty * th, tx * tw
        bh = min(th, h - r0)
        bw = min(tw, w - c0)
        full[:, r0:r0 + bh, c0:c0 + bw] = np.moveaxis(tile[:bh, :bw, :], -1, 0)
    return full, reuse


# --- Writer -----------------------------------------------------------------
cdef class GeotiffWriter:
    """Hand-rolled GeoTIFF / COG write driver.

    Parameters
    ----------
    file : Path | str
        The output path.
    crs : str, optional
        A user provided spatial reference system if none is set explicitly.
    """

    # State and pathing
    cdef readonly str path
    cdef object _crs
    cdef bint _closed

    # Grid geometry
    cdef readonly object profile
    cdef int _w
    cdef int _h
    cdef int _tw
    cdef int _th

    # Data model
    cdef readonly dict variables
    cdef list _variables
    cdef str _dtype
    cdef int _sample_format
    cdef int _bits
    cdef object _nodata
    cdef bint _has_nodata
    cdef int _compression
    cdef int _complevel

    # Georeferencing
    cdef bint _has_pixel_scale
    cdef tuple _pixel_scale
    cdef bint _has_tiepoint
    cdef tuple _tiepoint
    cdef int _epsg
    cdef int _model_type
    cdef str _citation

    # Serial buffer / parallel scratch state
    cdef object _full
    cdef bint _parallel
    cdef object _scratch_path
    cdef object _scratch_fd
    cdef object _lock
    cdef int _nbx
    cdef int _ntiles0
    cdef dict _records

    def __init__(self, file, crs=None):
        from pathlib import Path

        self.path = Path(file).as_posix()
        self._crs = crs
        self._closed = False

        # Grid geometry.
        self.profile = None
        self._w = 0
        self._h = 0
        self._tw = 512
        self._th = 512

        # Data model.
        self.variables = {}
        self._variables = []
        self._dtype = "float32"
        self._sample_format = 3
        self._bits = 32
        self._nodata = NODATA_VALUE
        self._has_nodata = True
        self._compression = 8
        self._complevel = 5

        # Georeferencing.
        self._has_pixel_scale = False
        self._pixel_scale = (0.0, 0.0, 0.0)
        self._has_tiepoint = False
        self._tiepoint = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        self._epsg = 0
        self._model_type = 1
        self._citation = ""

        # Serial buffer / parallel scratch state.
        self._full = None
        self._parallel = False
        self._scratch_path = None
        self._scratch_fd = None
        self._lock = None
        self._nbx = 0
        self._ntiles0 = 0
        self._records = {}

    # --- Container protocol ------------------------------------------------
    def __getitem__(self, idx):
        return self._variables[idx]

    def __iter__(self):
        return iter(self._variables)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def __reduce__(self):
        return self.__class__, (self.path, self._crs)

    @property
    def closed(self):
        """Return whether the dataset has been closed."""
        return self._closed

    @property
    def names(self):
        """Return the band names."""
        return list(self.variables.keys())

    @property
    def size(self):
        """Return the number of bands."""
        return len(self.variables)

    # --- Configuration -----------------------------------------------------
    def set_block_size(self, tile_width, tile_height=None):
        """Set the (COG) tile size; also the parallel write granularity."""
        self._tw = int(tile_width)
        self._th = int(tile_height if tile_height is not None else tile_width)

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

    def create_spatial_variable(self, var, dtype="f4", nodata=NODATA_VALUE,
                                compression="deflate", complevel=6):
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
        # Resolve the compression codec and level
        if compression not in _COMPRESSION_CODES:
            raise ValueError(f"Unsupported compression: {compression!r}")
        self._compression = _COMPRESSION_CODES[compression]
        self._complevel = int(complevel)

        # Register the band and return it
        band = GeotiffWriterBand(self, len(self._variables), var)
        self.variables[var] = band
        self._variables.append(band)
        return band

    # --- Serial write ------------------------------------------------------
    cpdef _set_serial(self, int index, object data, object origin):
        """Write a window of one band into the in-memory full-resolution buffer."""
        # Allocate the buffer lazily once the band count is known
        if self._full is None:
            self._full = np.full((self.size, self._h, self._w), self._nodata,
                                 dtype=self._dtype)
        # Place the data at its (x, y) origin
        h, w = data.shape
        x0, y0 = int(origin[0]), int(origin[1])
        self._full[index, y0:y0 + h, x0:x0 + w] = data

    # --- Parallel write ----------------------------------------------------
    def start_parallel(self, ctx):
        """Set up the shared scratch file and lock for child-process writes.

        Returns the cross-process lock to pass to workers (alongside
        :meth:`sink_descriptor`).
        """
        if self._w == 0 or self._h == 0:
            raise ValueError("create_spatial_dims must be called before start_parallel")
        # Tile grid over the full raster
        nbx = (self._w + self._tw - 1) // self._tw
        nby = (self._h + self._th - 1) // self._th
        self._nbx = nbx
        self._ntiles0 = nbx * nby

        # Fresh scratch file for the compressed tiles plus the shared lock
        self._scratch_path = self.path + ".scratch"
        self._scratch_fd = os.open(
            self._scratch_path, os.O_RDWR | os.O_CREAT | os.O_TRUNC, 0o600
        )
        self._lock = ctx.Lock()
        self._parallel = True
        self._records = {}
        return self._lock

    def sink_descriptor(self):
        """Return a picklable descriptor workers use to build a :class:`TileSink`."""
        if not self._parallel:
            raise ValueError("start_parallel must be called first")
        return {
            "scratch": self._scratch_path,
            "tile_width": self._tw,
            "tile_height": self._th,
            "nbx": self._nbx,
            "samples_per_pixel": self.size,
            "nodata": self._nodata,
            "complevel": self._complevel,
            "compression": self._compression,
            "dtype": self._dtype,
        }

    cpdef collect_records(self, object results):
        """Register the ``(tile_id, offset, byte_count)`` records workers wrote.

        ``results`` may be an iterable of such tuples or of lists of them (as
        returned by the worker pool).
        """
        for item in results:
            if item is None:
                continue
            if isinstance(item, tuple) and len(item) == 3 and \
                    not isinstance(item[0], (list, tuple)):
                recs = [item]
            else:
                recs = item
            for tid, off, bc in recs:
                self._records[int(tid)] = (int(off), int(bc))

    # --- COG finalisation --------------------------------------------------
    cdef void _write_cog(self, object full, object reuse) except *:
        """Assemble and write the final COG from the full-resolution raster."""
        cdef int spp = full.shape[0]
        # Level 0 blobs: reuse already-compressed tiles where available.
        cdef int nbx = (self._w + self._tw - 1) // self._tw
        cdef int nby = (self._h + self._th - 1) // self._th
        cdef list level0 = []
        cdef int tx, ty, tid
        for ty in range(nby):
            for tx in range(nbx):
                tid = ty * nbx + tx
                if reuse and tid in reuse:
                    level0.append(reuse[tid])
                else:
                    raw = _tile_bytes(full, tx, ty, self._tw, self._th,
                                      self._nodata, self._dtype)
                    if self._compression == 8:
                        level0.append(deflate_tile(raw, self._complevel))
                    else:
                        level0.append(raw)
        cdef list level_blobs = [level0]
        cdef list level_w = [self._w]
        cdef list level_h = [self._h]

        # Overview pyramid down to a single tile.
        cur = full
        while cur.shape[2] > self._tw or cur.shape[1] > self._th:
            cur = _downsample(cur, self._sample_format, self._has_nodata,
                              self._nodata, self._dtype)
            level_blobs.append(_compress_level(cur, self._tw, self._th,
                                               self._nodata, self._dtype,
                                               self._compression, self._complevel))
            level_w.append(cur.shape[2])
            level_h.append(cur.shape[1])

        # Byte size of every tile per level (drives the IFD layout).
        level_bc = [[len(b) for b in lvl] for lvl in level_blobs]
        spec_d = {
            "width": self._w, "height": self._h,
            "tile_width": self._tw, "tile_height": self._th,
            "samples_per_pixel": spp, "bits_per_sample": self._bits,
            "sample_format": self._sample_format, "compression": self._compression,
            "predictor": 1,
            "has_nodata": self._has_nodata, "nodata": float(self._nodata or 0),
            "has_pixel_scale": self._has_pixel_scale, "pixel_scale": self._pixel_scale,
            "has_tiepoint": self._has_tiepoint, "tiepoint": self._tiepoint,
            "model_type": self._model_type, "raster_type": 1, "epsg": self._epsg,
            "crs_citation": self._citation,
            "gdal_nodata_ascii": (repr(self._nodata) if self._has_nodata else ""),
            "gdal_metadata_xml": _gdal_metadata_xml(self._variables),
        }
        # Build the header-first IFD chain and stream the tiles after it
        header, data_start, _ = _build_cog_header_py(spec_d, level_w, level_h,
                                                     level_bc)
        with open(self.path, "wb") as f:
            f.write(header)
            if len(header) < data_start:
                f.write(b"\x00" * (data_start - len(header)))
            for lvl in level_blobs:
                for blob in lvl:
                    f.write(blob)

    # --- I/O ----------------------------------------------------------------
    def flush(self):
        """No-op; data is written atomically on close."""

    def close(self):
        """Finalise and write the COG, releasing any parallel resources."""
        if self._closed:
            return
        try:
            if self._parallel:
                # Rebuild the raster from the worker-written scratch tiles
                full, reuse = _reconstruct_full(
                    self._records, self._scratch_fd, self.size, self._h,
                    self._w, self._th, self._tw, self._bits, self._compression,
                    self._nodata, self._dtype, self._nbx,
                )
                self._write_cog(full, reuse)
            elif self._full is not None:
                self._write_cog(self._full, None)
        finally:
            self._cleanup_parallel()
            self._closed = True

    cdef void _cleanup_parallel(self) except *:
        """Close and remove the scratch file and release parallel state."""
        if self._scratch_fd is not None:
            try:
                os.close(self._scratch_fd)
            except OSError:
                ...
            self._scratch_fd = None
        if self._scratch_path is not None and os.path.isfile(self._scratch_path):
            try:
                os.remove(self._scratch_path)
            except OSError:
                ...
            self._scratch_path = None
