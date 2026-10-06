# cython: language_level=3
# distutils: language = c++
"""GeoTIFF/ COG reader."""

import os
from pathlib import Path

import numpy as np

from libc.stdint cimport uint8_t, uint32_t, uint64_t

from fiat.driver.geotiff.bindings cimport (
    IfdInfo,
    TiffInfo,
    inflate_block,
    parse_tiff,
)
from fiat.driver.raster cimport GridProfile

__all__ = ["GeotiffReader", "GeotiffBand"]


# (sample_format, bits_per_sample) -> numpy base type character.
cdef dict _DTYPE_MAP = {
    (1, 8): "u1", (1, 16): "u2", (1, 32): "u4", (1, 64): "u8",
    (2, 8): "i1", (2, 16): "i2", (2, 32): "i4", (2, 64): "i8",
    (3, 32): "f4", (3, 64): "f8",
}


cdef class GeotiffBand:
    """A single raster band of a :class:`GeotiffReader`."""

    cdef dict _attrs
    cdef object _data
    cdef readonly object _dtype
    cdef readonly object _nodata
    cdef GeotiffReader _reader
    cdef object _reader_ref
    cdef readonly int index
    cdef readonly str name

    def __cinit__(self):
        # Set the attributes
        self._attrs = {}
        self._data = None
        self._dtype = None
        self._nodata = None
        self._reader = None
        self.index = 0
        self.name = ""

    @staticmethod
    cdef GeotiffBand _create(
        GeotiffReader reader, int index, str name, object nodata,
        object dtype, dict attrs,
    ):
        cdef GeotiffBand obj = GeotiffBand.__new__(GeotiffBand)
        obj._attrs = attrs
        obj._data = None
        obj._dtype = dtype
        obj._nodata = nodata
        obj._reader = reader
        obj.index = index
        obj.name = name

        return obj

    def __getitem__(self, select):
        return self._data[select]

    @property
    def data(self):
        """Return the data in memory."""
        return self._data

    @property
    def dtype(self):
        """Return the NumPy data type of the band."""
        return self._dtype

    @property
    def nodata(self):
        """Return the nodata value, or ``None``."""
        return self._nodata

    # I/O related
    def clear(self):
        """Release a data from memory."""
        self._data = None

    def load(self, *window):
        """Read a window of data into memory, optionally caching it."""
        select = slice(None) if not window else window
        data = self._reader._read_select(self.index, select)
        self._data = data
        return self._data

    # Get methods
    def get_attr(self, var):
        """Get a per-band metadata attribute by name."""
        return self._attrs[var]


cdef class GeotiffReader:
    """Read-only hand-rolled GeoTIFF driver.

    Parameters
    ----------
    file : Path | str
        The path to the TIFF file.
    crs : str, optional
        A user provided spatial reference system if the file has none.
    """

    cdef bytes _data
    cdef const uint8_t* _ptr
    cdef size_t _len
    cdef readonly str path
    cdef bint _closed

    # Full-resolution layout.
    cdef uint32_t _w
    cdef uint32_t _h
    cdef uint32_t _tw
    cdef uint32_t _th
    cdef uint32_t _rps
    cdef int _spp
    cdef int _bps
    cdef int _sf
    cdef int _comp
    cdef int _pred
    cdef bint _tiled
    cdef bint _be
    cdef object _dtype_file   # dtype with the file's byte order
    cdef object _dtype_native
    cdef object _tile_off     # np.ndarray[uint64]
    cdef object _tile_bc      # np.ndarray[uint64]

    cdef readonly GridProfile profile
    cdef readonly dict variables
    cdef readonly object _crs
    cdef list _variables

    def __cinit__(self, file, crs=None):
        # State and pathing
        self.path = Path(file).as_posix()
        if not os.path.isfile(self.path):
            raise FileNotFoundError(f"{self.path} doesn't exist, can't read")
        self._closed = False
        self._crs = crs

        # Read the whole file into memory once; tiles are seeked into by byte
        # offset over this buffer (the pointer stays valid while _data lives).
        with open(self.path, "rb") as fh:
            self._data = fh.read()
        self._len = len(self._data)
        self._ptr = <const uint8_t*><char*>self._data

        # Parse the TIFF structure via the C++ layer
        cdef TiffInfo info
        if parse_tiff(self._ptr, self._len, info) == 0:
            raise ValueError(f"{self.path} is not a supported TIFF file")

        # Copy the layout, build the spatial profile and the bands
        self._parse_layout(info)
        self._build_profile(info)
        self._build_bands(info)

    # Dunder methods
    def __dealloc__(self):
        self._ptr = NULL

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
        return self.__class__, (self.path, self._crs)

    # Private methods
    cdef void _build_bands(self, TiffInfo& info) except *:
        # Collect the per-band metadata items (GDAL_METADATA) and the band
        # descriptions that double as band names.
        cdef size_t i
        band_attrs = [dict() for _ in range(self._spp)]
        band_names = [None] * self._spp
        for i in range(info.meta_items.size()):
            name = info.meta_items[i].name.decode("utf-8", "replace")
            value = info.meta_items[i].value.decode("utf-8", "replace")
            sample = info.meta_items[i].sample
            if 0 <= sample < self._spp:
                band_attrs[sample][name] = value
                if name == "DESCRIPTION":
                    band_names[sample] = value

        # A single nodata value applies to every band
        nodata = None
        if info.has_nodata:
            nodata = info.nodata

        # Build one band per sample, falling back to a generic name
        self.variables = {}
        self._variables = []
        for i in range(self._spp):
            name = band_names[i] if band_names[i] else f"band_{i + 1}"
            band = GeotiffBand._create(
                self, i, name, nodata, self._dtype_native, band_attrs[i]
            )
            self.variables[name] = band
            self._variables.append(band)

    cdef void _build_profile(self, TiffInfo& info) except *:
        cdef double x0, y0, dx, dy
        # Resolve the CRS: EPSG geo-key first, then an embedded WKT citation,
        # then any user-supplied override.
        crs_wkt = None
        if info.epsg != 0:
            crs_wkt = f"EPSG:{info.epsg}"
        elif info.crs_citation.size():
            crs_wkt = info.crs_citation.decode("utf-8", "replace")
        elif self._crs is not None:
            crs_wkt = self._crs

        if info.has_pixel_scale and info.has_tiepoint:
            # Derive the geotransform from the pixel scale + tiepoint, then build
            # the cell-centre coordinate arrays the shared profile expects.
            dx = info.pixel_scale[0]
            dy = -info.pixel_scale[1]
            x0 = info.tiepoint[3] - info.tiepoint[0] * dx
            y0 = info.tiepoint[4] - info.tiepoint[1] * dy
            xvals = x0 + dx * (np.arange(self._w) + 0.5)
            yvals = y0 + dy * (np.arange(self._h) + 0.5)
            self.profile = GridProfile(xvals=xvals, yvals=yvals, crs_wkt=crs_wkt)
        else:
            # Without georeferencing only the shape is known
            self.profile = GridProfile(crs_wkt=crs_wkt)
            self.profile.shape = (self._h, self._w)
            self.profile.shape_xy = (self._w, self._h)

    cdef object _load_block(self, Py_ssize_t block_id, Py_ssize_t block_rows,
                            Py_ssize_t block_cols):
        """Decode one tile/strip into a (rows, cols, spp) native-dtype array."""
        cdef uint64_t off = self._tile_off[block_id]
        cdef uint64_t bc = self._tile_bc[block_id]
        cdef Py_ssize_t npix = block_rows * block_cols * self._spp
        cdef Py_ssize_t nbytes = npix * (self._bps // 8)
        cdef uint8_t[::1] dst_mv
        cdef size_t n

        # Raw blocks are viewed in place; DEFLATE blocks inflate into a buffer
        if self._comp == 1:
            arr = np.frombuffer(self._data, dtype=self._dtype_file,
                                count=npix, offset=off)
        else:
            dst = np.empty(nbytes, dtype=np.uint8)
            dst_mv = dst
            n = inflate_block(self._ptr + off, bc, &dst_mv[0], nbytes)
            if n != <size_t>nbytes:
                raise ValueError("DEFLATE tile decompression failed")
            arr = dst.view(self._dtype_file)

        # Shape as (rows, cols, samples), swap to native order, undo prediction
        arr = arr.reshape(block_rows, block_cols, self._spp)
        if self._be:
            arr = arr.astype(self._dtype_native)
        if self._pred == 2:
            arr = np.cumsum(arr, axis=1, dtype=self._dtype_native)
        return np.ascontiguousarray(arr, dtype=self._dtype_native)

    cdef void _parse_layout(self, TiffInfo& info) except *:
        cdef IfdInfo* ifd = &info.ifds[0]
        # Copy the full-resolution layout (overviews are read-through only)
        self._be = info.big_endian
        self._w = ifd.width
        self._h = ifd.height
        self._tw = ifd.tile_width
        self._th = ifd.tile_height
        self._rps = ifd.rows_per_strip
        self._spp = ifd.samples_per_pixel
        self._bps = ifd.bits_per_sample
        self._sf = ifd.sample_format
        self._comp = ifd.compression
        self._pred = ifd.predictor
        self._tiled = ifd.is_tiled

        # Guard against the codecs/predictors/dtypes we don't support
        if self._comp not in (1, 8):
            raise NotImplementedError(
                f"TIFF compression {self._comp} is not supported (only none/deflate)"
            )
        if self._pred not in (1, 2):
            raise NotImplementedError(
                f"TIFF predictor {self._pred} is not supported (only none/horizontal)"
            )
        key = (self._sf, self._bps)
        if key not in _DTYPE_MAP:
            raise NotImplementedError(
                f"TIFF sample format {self._sf} / {self._bps}-bit is not supported"
            )

        # Resolve the numpy dtype in both the file and the native byte order
        base = _DTYPE_MAP[key]
        order = ">" if self._be else "<"
        self._dtype_file = np.dtype(order + base)
        self._dtype_native = np.dtype(base)

        # Copy the tile/strip offset + byte-count arrays into numpy buffers
        cdef size_t n = ifd.tile_offsets.size()
        cdef size_t i
        off = np.empty(n, dtype=np.uint64)
        bc = np.empty(n, dtype=np.uint64)
        cdef uint64_t[::1] off_mv = off
        cdef uint64_t[::1] bc_mv = bc
        for i in range(n):
            off_mv[i] = ifd.tile_offsets[i]
            bc_mv[i] = ifd.tile_bytecounts[i]
        self._tile_off = off
        self._tile_bc = bc

    cdef object _read_region(self, int bidx, Py_ssize_t r0, Py_ssize_t r1,
                             Py_ssize_t c0, Py_ssize_t c1):
        """Read band ``bidx`` over the pixel window ``[r0:r1, c0:c1]``."""
        cdef Py_ssize_t out_h = r1 - r0
        cdef Py_ssize_t out_w = c1 - c0
        out = np.empty((out_h, out_w), dtype=self._dtype_native)

        # Block grid: square tiles, or full-width strips of rows_per_strip rows
        cdef Py_ssize_t bw, bh, nbx, bx0, bx1, by0, by1, bx, by
        cdef Py_ssize_t bid, brows, bcols, br0, bc0, tr0, tr1, tc0, tc1
        if self._tiled:
            bw = self._tw
            bh = self._th
        else:
            bw = self._w
            bh = self._rps if self._rps > 0 else self._h
        nbx = (self._w + bw - 1) // bw

        # The range of blocks that intersect the requested window
        bx0 = c0 // bw
        bx1 = (c1 - 1) // bw
        by0 = r0 // bh
        by1 = (r1 - 1) // bh
        for by in range(by0, by1 + 1):
            for bx in range(bx0, bx1 + 1):
                # Decode the block (tiles are padded, strips are clipped)
                bid = by * nbx + bx
                br0 = by * bh
                bc0 = bx * bw
                if self._tiled:
                    brows = bh
                    bcols = bw
                else:
                    brows = min(bh, self._h - br0)
                    bcols = self._w
                block = self._load_block(bid, brows, bcols)
                # Copy the overlapping sub-rectangle into the output
                tr0 = max(r0, br0)
                tr1 = min(r1, br0 + brows)
                tc0 = max(c0, bc0)
                tc1 = min(c1, bc0 + bcols)
                out[tr0 - r0:tr1 - r0, tc0 - c0:tc1 - c0] = \
                    block[tr0 - br0:tr1 - br0, tc0 - bc0:tc1 - bc0, bidx]
        return out

    cdef object _read_select(self, int bidx, object select):
        """Normalise a NumPy-style selection to a pixel window and read it."""
        cdef Py_ssize_t r0, r1, c0, c1
        # Full read, a (row, col) slice/index pair, or a single row slice
        if select is None or (isinstance(select, slice) and select == slice(None)):
            r0, r1, c0, c1 = 0, self._h, 0, self._w
        elif isinstance(select, tuple) and len(select) == 2:
            rs, cs = select
            r0, r1, _ = (
                rs.indices(self._h) if isinstance(rs, slice) else (rs, rs + 1, 1)
            )
            c0, c1, _ = (
                cs.indices(self._w) if isinstance(cs, slice) else (cs, cs + 1, 1)
            )
        elif isinstance(select, slice):
            r0, r1, _ = select.indices(self._h)
            c0, c1 = 0, self._w
        else:
            raise TypeError(f"Unsupported selection: {select!r}")
        return self._read_region(bidx, r0, r1, c0, c1)

    # Properties
    @property
    def closed(self):
        """Return whether the dataset has been closed."""
        return self._closed

    @property
    def names(self):
        """Return the names of the bands."""
        return list(self.variables.keys())

    @property
    def size(self):
        """Return the number of bands."""
        return len(self.variables)

    # I/O methods
    def close(self):
        """Close the dataset."""
        self._closed = True
        self._data = None
        self._ptr = NULL

    def flush(self):
        """No-op for a read-only dataset."""

    def load(
        self,
        *window: tuple[slice, ...],
    ) -> None:
        """Load spatial variables into memory."""
        for var in self._variables:
            _ = var.load(*window)
