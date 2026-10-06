# Hand-rolled GeoTIFF / COG driver

A small, self-contained Cython + C++ driver that reads and writes tiled,
DEFLATE-compressed GeoTIFFs **without** libtiff, libgeotiff or GDAL. It writes
both **plain** GeoTIFFs and strict **Cloud Optimized GeoTIFFs** (COGs), mirrors
the public surface of the netCDF grid driver (`fiat.driver.netcdf`) so it is a
drop-in replacement, and additionally supports **direct writes from child
processes** to a single shared output file.

This is FIAT-authored code (not vendored). The only external dependency is
**zlib** (DEFLATE), added as a conda/pixi **build** dependency; see
`pyproject.toml` (`[tool.pixi.dependencies] zlib`). The header is located at build
time via `setup.py:_include_directories()`, and `_geotiff_ext()` links zlib
**statically** (embedding `libz.a` via `_zlib_link_kwargs()`) so the compiled
extensions carry no runtime zlib dependency; it falls back to dynamic `-lz`
linking only where no static archive is available.

## Layout

| File | Role |
| --- | --- |
| `tiff_c.h` / `tiff_c.cpp` | C++ codec: TIFF parse, DEFLATE (de)compress, all GeoTIFF/COG structure building (IFDs, GeoKeys, GDAL_METADATA XML, GDAL_NODATA), and the per-tile pixel work (`encode_tile` pad+chunky-interleave, `downsample_tile` nodata-aware 2x2 overview average). Never touches files. |
| `bindings.pxd` | Cython declarations of the C++ layer. |
| `reader.pyx` | `GeotiffReader` / `GeotiffBand` — windowed reads into NumPy arrays. |
| `writer.pyx` | `GeotiffWriter` (serial + parallel), `TileSink`, zlib helpers. |

File positioning, the cross-process write lock and all multiprocessing live on
the Python/Cython side; the C++ layer is a pure codec that only builds/parses
byte structures and transforms tile buffers. This split mirrors the FlatGeobuf
driver (`fiat.driver.fgb`).

## Plain vs COG

`GeotiffWriter(file, crs=None, cog=True)` selects the output layout (also
threaded through `create_geotiff_handle()` and `open_grid(..., cog=...)`):

* **COG** (`cog=True`, default): a header-first IFD chain (full resolution
  followed by an average-resampled overview pyramid down to a single tile). The
  header region is reserved up front — its size is fully determined by geometry —
  so tiles can be streamed in and the header patched afterwards.
* **plain** (`cog=False`): a single full-resolution IFD, **no overviews**, with
  the IFD written *last* (classic TIFF allows the IFD anywhere; the 8-byte header
  simply points to it). This lets tiles stream straight to the file with no
  reserved region.

The **reader** needs no flag: `parse_tiff` follows the TIFF header's first-IFD
pointer wherever it lands and always reads `ifds[0]` (the full-resolution level),
so it transparently reads plain files, COGs, tiled or strip layouts.

## Streaming write model (no scratch file)

Both layouts write compressed tiles **directly into the final output file** — the
full raster is never materialised in memory and there is no scratch file:

1. `GeotiffWriter.start_parallel(ctx)` opens the output, reserves the COG header
   region (or an 8-byte placeholder for plain) and creates a cross-process lock.
2. Each worker builds a `TileSink` (from `sink_descriptor()` + the lock),
   compresses its tile(s) and **appends** them to the shared output under the
   lock (`lseek(SEEK_END)` + `write`), returning `(tile_id, offset, byte_count)`
   records. The parent collects these via `collect_records` (no shared memory).
3. On `close()` the parent builds the COG overview pyramid **incrementally** —
   each overview tile is the average-downsampled 2×2 block of parent tiles, read
   back from the file a block at a time — then writes the final header
   (`build_cog_header_fixed`, patched into the reserved region) or, for a plain
   file, appends the single trailing IFD (`build_plain_ifd`) and patches the
   8-byte header pointer.

The serial path offers two ways to write:

* `GeotiffWriter.write_window(origin, data)` — the streaming, bounded-memory
  path: a tile-aligned ``(bands, h, w)`` window is encoded and appended
  immediately, so the whole raster is never buffered (the in-process counterpart
  of a worker's `TileSink.write_block`). `NetcdfWriter` exposes the same
  `write_window` for API symmetry (netCDF streams per-variable, so it is a thin
  fan-out).
* `GeotiffWriterBand.set(data, origin)` — a convenience that buffers the band
  arrays and streams them on `close()` (needed because chunky tiles require all
  bands together; use `write_window` when memory matters).

Compression is a dataset-wide setting on the writer (`GeotiffWriter(...,
compression="deflate", complevel=5)`), not per band; `NetcdfWriter` matches this
(`compression="zlib"` default).

> **Tile ordering note.** Because full-resolution tiles are streamed first and
> overviews appended afterwards, the on-disk *tile data* is not in GDAL's
> canonical COG block order (overviews-before-main). The file is header-first,
> carries a valid overview pyramid and is read correctly by GDAL/QGIS; it is not
> guaranteed to pass GDAL's strict `validate_cloud_optimized_geotiff` block-order
> check. This is an intrinsic consequence of single-pass streaming (and matches
> the driver's earlier behaviour).

## Scope and limitations

* **Write**: tiled, chunky (band-interleaved), classic (32-bit) TIFF; DEFLATE
  (compression 8) or uncompressed; float32 output by default (other dtypes via
  `create_spatial_variable(dtype=...)`); predictor 1 (none). Plain (single IFD,
  IFD-last) or COG (header-first IFD chain with an average-resampled overview
  pyramid).
* **Read**: classic TIFF, little/big endian; tiled or stripped; compression 1
  (none) or 8 (DEFLATE); predictor 1 (none) or 2 (horizontal); sample formats
  uint/int (8/16/32-bit) and IEEE float (32/64-bit). Unsupported inputs raise a
  clear error.
* **CRS**: encoded with standard GeoTIFF GeoKeys from the `pyproj` EPSG code
  (`ProjectedCSTypeGeoKey` / `GeographicTypeGeoKey`), with the full WKT embedded
  as a citation fallback when the CRS has no EPSG code.
* **nodata**: written to the GDAL_NODATA tag (42113) as a plain `%.18g` numeric
  string, formatted in the C++ codec from the `double` value. Formatting on the
  C++ side avoids language-specific reprs (e.g. NumPy's `np.float32(-9999.0)`)
  that GDAL / QGIS cannot parse and would silently ignore.
* **Not supported (v1)**: BigTIFF (> 4 GiB) — detected and rejected on read, and
  never written; LZW/other codecs; floating-point predictor (3) on read.

## Specifications followed

Cited in `tiff_c.{h,cpp}` at the relevant sites:

* TIFF 6.0 (Adobe, 1992) — header, IFD, tags, tiling, `SampleFormat`.
* TIFF Technical Note 2 — Adobe Deflate (compression 8).
* OGC GeoTIFF 1.1 (OGC 19-008r4) — `ModelPixelScaleTag` (33550),
  `ModelTiepointTag` (33922), `GeoKeyDirectoryTag` (34735),
  `GeoAsciiParamsTag` (34737) and the geo-keys.
* OGC Cloud Optimized GeoTIFF 1.0 (OGC 21-026) — header-first IFD layout, tiled,
  overviews ordered full-resolution → coarsest.
* GDAL conventions — `GDAL_NODATA` (42113) ASCII, `GDAL_METADATA` (42112) XML
  with per-band `<Item name=... sample=...>` entries (used to round-trip band
  names and attributes).
* zlib manual (`compress2` / `uncompress`), zlib 1.3.

## Rebuilding

The extensions are built like the rest of FIAT:

```sh
pixi run python setup.py build_ext --inplace
```
