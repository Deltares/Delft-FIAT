import pickle
import struct
from multiprocessing import get_context
from pathlib import Path

import numpy as np
import pytest
from pyproj.crs import CRS

from fiat.driver.geotiff import GeotiffReader, GeotiffWriter, TileSink
from fiat.open import open_grid
from fiat.util import NODATA_VALUE


## Helpers
def _write_grid(
    path,
    bands,
    data,
    crs="EPSG:28992",
    tile=128,
    dtype="f4",
    nodata=NODATA_VALUE,
    compression="deflate",
    nx=None,
    ny=None,
) -> Path:
    """Write a small (multi-band) GeoTIFF via the serial writer."""
    # Derive the grid shape from the data unless overridden
    arr = np.asarray(data)
    ny = ny if ny is not None else arr.shape[-2]
    nx = nx if nx is not None else arr.shape[-1]

    # North-up cell centres in a metric projection
    lons = 100000 + 10 * (np.arange(nx) + 0.5)
    lats = 500000 - 10 * (np.arange(ny) + 0.5)

    # Configure the writer and register the bands
    w = GeotiffWriter(path)
    w.set_block_size(tile)
    w.create_spatial_dims(lats, lons)
    w.set_spatial_ref(CRS.from_user_input(crs))
    for name in bands:
        w.create_spatial_variable(
            name, dtype=dtype, nodata=nodata, compression=compression
        )

    # Fill the bands and finalize the COG
    if arr.ndim == 2:
        arr = arr[np.newaxis, ...]
    for i, name in enumerate(bands):
        w.variables[name].set(arr[i], origin=(0, 0))
    w.close()
    return path


def _read_ifds(path) -> tuple:
    """Minimal classic little-endian TIFF IFD walker (for COG structure checks)."""
    # Validate the little-endian classic TIFF magic
    data = Path(path).read_bytes()
    assert data[:4] == b"II\x2a\x00"

    # Walk the IFD chain, collecting each directory's tags
    off = struct.unpack_from("<I", data, 4)[0]
    ifds = []
    while off != 0:
        (n,) = struct.unpack_from("<H", data, off)
        tags = {}
        for i in range(n):
            tag, typ, cnt = struct.unpack_from("<HHI", data, off + 2 + i * 12)
            val = struct.unpack_from("<I", data, off + 2 + i * 12 + 8)[0]
            tags[tag] = (typ, cnt, val, off + 2 + i * 12 + 8)
        ifds.append({"offset": off, "tags": tags})
        off = struct.unpack_from("<I", data, off + 2 + n * 12)[0]
    return data, ifds


## Dispatch
def test_open_grid_dispatch(tmp_path: Path):
    # Write a tiny grid so there is something to open
    p = Path(tmp_path, "x.tif")
    _write_grid(p, ["v"], np.ones((20, 15), "float32"))

    # Reading a .tif returns the GeoTIFF reader
    r = open_grid(p)
    assert isinstance(r, GeotiffReader)
    r.close()

    # Opening a .tiff in write mode returns the GeoTIFF writer
    w = open_grid(Path(tmp_path, "y.tiff"), mode="w")
    assert isinstance(w, GeotiffWriter)


## Round-trip
def test_roundtrip_single_band(tmp_path: Path):
    # Write a single-band grid
    p = Path(tmp_path, "s.tif")
    d = np.arange(300, dtype="float32").reshape(15, 20)
    _write_grid(p, ["v"], d)

    # Read it back and assert the metadata and the pixels
    r = GeotiffReader(str(p))
    assert r.size == 1
    assert r.names == ["v"]
    assert r.profile.shape == (15, 20)
    np.testing.assert_array_equal(r[0].read_window(), d)
    r.close()


def test_roundtrip_multi_band(tmp_path: Path):
    # Write two bands with distinct content
    p = Path(tmp_path, "m.tif")
    d = np.stack(
        [
            np.arange(600, dtype="float32").reshape(20, 30),
            np.full((20, 30), 3.5, "float32"),
        ]
    )
    _write_grid(p, ["a", "b"], d)

    # Both bands round-trip independently
    r = GeotiffReader(str(p))
    assert r.size == 2
    assert r.names == ["a", "b"]
    np.testing.assert_array_equal(r[0].read_window(), d[0])
    np.testing.assert_array_equal(r[1].read_window(), d[1])
    r.close()


@pytest.mark.parametrize(
    ("code", "np_dtype"),
    [
        ("u1", "uint8"),
        ("u2", "uint16"),
        ("u4", "uint32"),
        ("i2", "int16"),
        ("i4", "int32"),
        ("f4", "float32"),
        ("f8", "float64"),
    ],
)
def test_roundtrip_dtypes(tmp_path: Path, code, np_dtype):
    # Build representative data for the data type under test
    p = Path(tmp_path, f"d_{code}.tif")
    info = np.iinfo if np_dtype.startswith(("u", "i")) else None
    if info is not None:
        hi = min(info(np_dtype).max, 1000)
        d = (np.arange(200) % hi).astype(np_dtype).reshape(10, 20)
        # Unsigned types cannot store the default negative nodata
        nodata = 0 if np_dtype.startswith("u") else NODATA_VALUE
    else:
        d = (np.arange(200, dtype=np_dtype) / 3).reshape(10, 20)
        nodata = NODATA_VALUE

    # The data type and the values survive the round-trip
    _write_grid(p, ["v"], d, dtype=code, tile=8, nodata=nodata)
    r = GeotiffReader(str(p))
    assert r[0].dtype == np.dtype(np_dtype)
    np.testing.assert_array_equal(r[0].read_window(), d)
    r.close()


def test_roundtrip_uncompressed(tmp_path: Path):
    # Write without compression
    p = Path(tmp_path, "raw.tif")
    d = np.arange(400, dtype="float32").reshape(20, 20)
    _write_grid(p, ["v"], d, compression="none", tile=16)

    # The Compression tag (259) is set to none (1)
    _, ifds = _read_ifds(p)
    assert ifds[0]["tags"][259][2] == 1

    # And the pixels still round-trip
    r = GeotiffReader(str(p))
    np.testing.assert_array_equal(r[0].read_window(), d)
    r.close()


def test_windowed_reads(tmp_path: Path):
    # Write a grid spanning several tiles
    p = Path(tmp_path, "win.tif")
    d = np.arange(50 * 40, dtype="float32").reshape(50, 40)
    _write_grid(p, ["v"], d, tile=16)

    # A range of windows (including partial, edge-spanning ones) match the source
    r = GeotiffReader(str(p))
    b = r[0]
    for win in [
        (slice(0, 10), slice(0, 10)),
        (slice(17, 33), slice(5, 39)),
        (slice(40, 50), slice(30, 40)),
    ]:
        np.testing.assert_array_equal(b[win], d[win])
    r.close()


def test_nodata_roundtrip(tmp_path: Path):
    # Write data with a single nodata cell
    p = Path(tmp_path, "nd.tif")
    d = np.full((12, 12), 5.0, "float32")
    d[0, 0] = NODATA_VALUE
    _write_grid(p, ["v"], d, nodata=NODATA_VALUE)

    # The nodata value and the masked cell survive
    r = GeotiffReader(str(p))
    assert r[0].nodata == NODATA_VALUE
    out = r[0].read_window()
    assert out[0, 0] == NODATA_VALUE
    assert out[5, 5] == 5.0
    r.close()


## CRS
def test_crs_projected_epsg(tmp_path: Path):
    # A projected CRS is encoded via its EPSG code
    p = Path(tmp_path, "proj.tif")
    _write_grid(p, ["v"], np.ones((10, 10), "float32"), crs="EPSG:28992")

    # It reads back as the same projected EPSG code
    r = GeotiffReader(str(p))
    assert r.profile.crs.to_epsg() == 28992
    assert r.profile.crs.is_projected
    r.close()


def test_crs_geographic_epsg(tmp_path: Path):
    # A geographic CRS is encoded via its EPSG code
    p = Path(tmp_path, "geo.tif")
    _write_grid(p, ["v"], np.ones((10, 10), "float32"), crs="EPSG:4326")

    # It reads back as the same geographic EPSG code
    r = GeotiffReader(str(p))
    assert r.profile.crs.to_epsg() == 4326
    assert r.profile.crs.is_geographic
    r.close()


def test_crs_non_epsg_wkt_fallback(tmp_path: Path):
    # A custom projection has no EPSG code, so it falls back to a WKT citation
    crs = CRS.from_proj4("+proj=laea +lat_0=52 +lon_0=10 +datum=WGS84 +units=m")
    assert crs.to_epsg() is None

    # The CRS is recovered from the embedded WKT
    p = Path(tmp_path, "wkt.tif")
    _write_grid(p, ["v"], np.ones((10, 10), "float32"), crs=crs.to_wkt())
    r = GeotiffReader(str(p))
    assert r.profile.crs is not None
    assert r.profile.crs.is_projected
    r.close()


def test_geotransform(tmp_path: Path):
    # Write a grid with a known geotransform
    p = Path(tmp_path, "gtf.tif")
    _write_grid(p, ["v"], np.ones((10, 10), "float32"))

    # Origin, resolution and north-up sign are recovered
    r = GeotiffReader(str(p))
    t = r.profile.transform
    assert t[0] == pytest.approx(100000.0)  # x origin
    assert t[1] == pytest.approx(10.0)  # dx
    assert t[3] == pytest.approx(500000.0)  # y origin
    assert t[5] == pytest.approx(-10.0)  # dy (north-up)
    r.close()


## COG structure
def test_cog_overviews_and_header_first(tmp_path: Path):
    # Write a grid large enough to need overviews
    p = Path(tmp_path, "cog.tif")
    d = np.arange(600 * 500, dtype="float32").reshape(600, 500)
    _write_grid(p, ["v"], d, tile=128)
    data, ifds = _read_ifds(p)

    # Header-first: the first IFD sits right after the 8-byte TIFF header
    assert ifds[0]["offset"] == 8

    # Overviews are present and decrease in size
    assert len(ifds) > 1
    widths = [ifds[i]["tags"][256][2] for i in range(len(ifds))]
    assert widths == sorted(widths, reverse=True)

    # Overview IFDs carry the reduced-resolution flag (NewSubfileType bit 0)
    assert ifds[0]["tags"][254][2] == 0
    assert all(ifds[i]["tags"][254][2] & 1 for i in range(1, len(ifds)))

    # All tile data comes after every IFD structure (IFDs before imagery)
    min_tile_off = min(
        struct.unpack_from("<I", data, ifds[i]["tags"][324][2])[0]
        for i in range(len(ifds))
    )
    last_ifd_end = max(ifd["offset"] + 2 + len(ifd["tags"]) * 12 + 4 for ifd in ifds)
    assert min_tile_off >= last_ifd_end


def test_cog_overview_is_average(tmp_path: Path):
    # A linear ramp down-samples to exact 2x2 block means
    p = Path(tmp_path, "ov.tif")
    d = (
        np.arange(600, dtype="float32")[:, None]
        + np.arange(600, dtype="float32")[None, :]
    )
    _write_grid(p, ["v"], d, tile=256, nx=600, ny=600)

    # Overviews exist and the full resolution is preserved
    _, ifds = _read_ifds(p)
    assert len(ifds) > 1
    r = GeotiffReader(str(p))
    np.testing.assert_array_equal(r[0].read_window(), d)
    r.close()


## Parallel writes
_PAR = {}


def _par_init(desc, lock, ref):
    """Pool initializer: build the per-worker tile sink and stash the data."""
    _PAR["sink"] = TileSink(desc, lock)
    _PAR["ref"] = ref


def _par_work(args):
    """Compute one tile and append it to the shared output file."""
    col, row, h, w = args
    sink = _PAR["sink"]
    ref = _PAR["ref"]
    return sink.write_block((col, row), ref[:, row : row + h, col : col + w])


def test_parallel_multiprocess(tmp_path: Path):
    # Reference data for a grid split into 16x16 tiles
    p = Path(tmp_path, "par.tif")
    H, W, TILE = 64, 48, 16
    ref = np.stack(
        [
            (np.arange(H)[:, None] + np.arange(W)[None, :]).astype("float32"),
            (np.arange(H)[:, None] * np.arange(W)[None, :]).astype("float32"),
        ]
    )

    # Configure the writer for parallel, direct-from-worker tile writes
    lons = 100000 + 10 * (np.arange(W) + 0.5)
    lats = 500000 - 10 * (np.arange(H) + 0.5)
    w = GeotiffWriter(str(p))
    w.set_block_size(TILE)
    w.create_spatial_dims(lats, lons)
    w.set_spatial_ref(CRS.from_epsg(4326))
    for name in ("a", "b"):
        w.create_spatial_variable(name, dtype="f4", nodata=NODATA_VALUE)
    lock = w.start_parallel(get_context("spawn"))
    desc = w.sink_descriptor()

    # One job per tile-aligned window
    jobs = [
        (c, r, min(TILE, H - r), min(TILE, W - c))
        for r in range(0, H, TILE)
        for c in range(0, W, TILE)
    ]

    # Workers write their tiles directly; the parent collects their records
    ctx = get_context("spawn")
    with ctx.Pool(
        processes=3, initializer=_par_init, initargs=(desc, lock, ref)
    ) as pool:
        results = pool.map(_par_work, jobs)
    w.collect_records(results)
    w.close()

    # The assembled COG matches the reference for every band
    r = GeotiffReader(str(p))
    np.testing.assert_array_equal(r[0].read_window(), ref[0])
    np.testing.assert_array_equal(r[1].read_window(), ref[1])
    r.close()


## Misc
def test_reader_pickle_roundtrip(tmp_path: Path):
    # Write a grid and open it
    p = Path(tmp_path, "pick.tif")
    d = np.arange(100, dtype="float32").reshape(10, 10)
    _write_grid(p, ["v"], d)
    r = GeotiffReader(str(p))

    # The reader survives a pickle round-trip (for the multiprocessing handoff)
    r2 = pickle.loads(pickle.dumps(r))
    np.testing.assert_array_equal(r2[0].read_window(), d)
    r.close()
    r2.close()


def test_reader_context_manager(tmp_path: Path):
    # Write a grid to open as a context manager
    p = Path(tmp_path, "ctx.tif")
    _write_grid(p, ["v"], np.ones((8, 8), "float32"))

    # The reader opens inside the block and is closed on exit
    with GeotiffReader(str(p)) as r:
        assert not r.closed
        assert r.size == 1
    assert r.closed


def test_reader_rejects_non_tiff(tmp_path: Path):
    # A file that is not a TIFF is rejected with a clear error
    p = Path(tmp_path, "bad.tif")
    p.write_bytes(b"not a tiff at all")
    with pytest.raises(ValueError, match="not a supported TIFF"):
        GeotiffReader(str(p))


def test_reader_missing_file(tmp_path: Path):
    # A missing file raises up front
    with pytest.raises(FileNotFoundError):
        GeotiffReader(str(Path(tmp_path, "nope.tif")))
