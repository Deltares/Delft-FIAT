# Hand-rolled GeoTIFF / COG driver

A small, self-contained Cython + C++ driver that reads and writes tiled,
DEFLATE-compressed, strict Cloud Optimized GeoTIFFs (COGs) **without** libtiff,
libgeotiff or GDAL. It mirrors the public surface of the netCDF grid driver
(`fiat.driver.netcdf`) so it is a drop-in replacement, and it additionally
supports **direct writes from child processes** to a single shared output file.

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
| `tiff_c.h` / `tiff_c.cpp` | C++ codec: TIFF parse, DEFLATE (de)compress, COG header assembly. Never touches files — it only transforms byte buffers. |
| `bindings.pxd` | Cython declarations of the C++ layer. |
| `reader.pyx` | `GeotiffReader` / `GeotiffBand` — windowed reads into NumPy arrays. |
| `writer.pyx` | `GeotiffWriter` (serial + parallel), `TileSink`, zlib helpers. |

File positioning, the cross-process write lock, overview down-sampling and all
multiprocessing live on the Python/Cython side; the C++ layer is a pure codec.
This split mirrors the FlatGeobuf driver.

## Parallel write model

Writing a single COG from many processes is reconciled with per-tile compression
as follows:

1. `GeotiffWriter.start_parallel(ctx)` creates a scratch file and a cross-process
   lock.
2. Each worker builds a `TileSink` (from `sink_descriptor()` + the lock),
   compresses its tile(s) and **appends** them to the scratch file under the
   lock (`lseek(SEEK_END)` + `write`), returning `(tile_id, offset, byte_count)`
   records.
3. The parent collects those records (`collect_records`), reconstructs the
   full-resolution raster, builds the overview pyramid and emits the final
   header-first COG in `close()`. Already-compressed full-resolution tiles are
   copied verbatim (no recompression); only overview tiles are compressed anew.

No shared memory is required — tile index records travel back through the worker
pool's return values.

## Scope and limitations

* **Write**: tiled, chunky (band-interleaved), classic (32-bit) TIFF; DEFLATE
  (compression 8) or uncompressed; float32 output by default (other dtypes via
  `create_spatial_variable(dtype=...)`); predictor 1 (none). Strict COG:
  header-first IFD chain, tiled, with an average-resampled overview pyramid down
  to a single tile.
* **Read**: classic TIFF, little/big endian; tiled or stripped; compression 1
  (none) or 8 (DEFLATE); predictor 1 (none) or 2 (horizontal); sample formats
  uint/int (8/16/32-bit) and IEEE float (32/64-bit). Unsupported inputs raise a
  clear error.
* **CRS**: encoded with standard GeoTIFF GeoKeys from the `pyproj` EPSG code
  (`ProjectedCSTypeGeoKey` / `GeographicTypeGeoKey`), with the full WKT embedded
  as a citation fallback when the CRS has no EPSG code.
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
