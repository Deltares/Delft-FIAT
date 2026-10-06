from multiprocessing import get_context
from pathlib import Path

import numpy as np
from fiat.driver.geotiff.writer import TileSink

from fiat.driver import NetcdfReader
from fiat.driver.geotiff import GeotiffReader, create_geotiff_handle
from fiat.util import NODATA_VALUE


## Handle creation
def test_create_geotiff_handle(
    tmp_path: Path,
    hazard_event_data: NetcdfReader,
):
    # Create the handle (the COG itself is only written on close)
    h = create_geotiff_handle(
        path=Path(tmp_path, "foo.tif"),
        variables=["data"],
        ds_like=hazard_event_data,
        crs=hazard_event_data.profile.crs,
    )

    # Assert the configured state
    assert h.profile.shape == (10, 10)
    assert h.size == 1
    assert h.names == ["data"]


def test_create_geotiff_handle_multiple(
    tmp_path: Path,
    hazard_event_data: NetcdfReader,
):
    # Create the handle with two bands
    h = create_geotiff_handle(
        path=Path(tmp_path, "foo.tif"),
        variables=["depth", "damage"],
        ds_like=hazard_event_data,
        crs=hazard_event_data.profile.crs,
    )

    # Assert both bands are registered in order
    assert h.profile.shape == (10, 10)
    assert h.size == 2
    assert h.names == ["depth", "damage"]


## Serial writing
def test_geotiff_writer_serial_roundtrip(
    tmp_path: Path,
    hazard_event_data: NetcdfReader,
):
    # Create the handle and set two bands of data
    p = Path(tmp_path, "serial.tif")
    h = create_geotiff_handle(
        path=p,
        variables=["a", "b"],
        ds_like=hazard_event_data,
        crs=hazard_event_data.profile.crs,
    )
    d0 = np.arange(100, dtype="float32").reshape(10, 10)
    d1 = d0 * 2
    h.variables["a"].set(d0, origin=(0, 0))
    h.variables["b"].set(d1, origin=(0, 0))
    h.close()

    # The COG is written and reads back exactly
    assert p.is_file()
    r = GeotiffReader(str(p))
    assert r.size == 2
    assert r.names == ["a", "b"]
    assert r.profile.crs.to_epsg() == hazard_event_data.profile.crs.to_epsg()
    np.testing.assert_array_equal(r[0].load(), d0)
    np.testing.assert_array_equal(r[1].load(), d1)
    r.close()


## Parallel writing
def test_geotiff_writer_parallel(
    tmp_path: Path,
    hazard_event_data: NetcdfReader,
):
    # Open the handle for parallel writes with a 5x5 tile (4 tiles total)
    p = Path(tmp_path, "parallel.tif")
    h = create_geotiff_handle(
        path=p,
        variables=["v"],
        ds_like=hazard_event_data,
        crs=hazard_event_data.profile.crs,
        tile=(5, 5),
    )
    lock = h.start_parallel(get_context("spawn"))
    desc = h.sink_descriptor()
    sink = TileSink(desc, lock)

    # Write each tile and collect the returned index records
    ref = np.arange(100, dtype="float32").reshape(10, 10)
    records = []
    for row in (0, 5):
        for col in (0, 5):
            block = ref[np.newaxis, row : row + 5, col : col + 5]
            records.append(sink.write_block((col, row), block))
    sink.close()

    # Finalize and assert the reassembled grid matches the reference
    h.collect_records(records)
    h.close()
    assert p.is_file()
    r = GeotiffReader(str(p))
    np.testing.assert_array_equal(r[0].load(), ref)
    r.close()


def test_geotiff_writer_parallel_nodata(
    tmp_path: Path,
    hazard_event_data: NetcdfReader,
):
    # Write a single tile that contains a nodata cell
    p = Path(tmp_path, "nodata.tif")
    h = create_geotiff_handle(
        path=p,
        variables=["v"],
        ds_like=hazard_event_data,
        crs=hazard_event_data.profile.crs,
        tile=(10, 10),
    )
    lock = h.start_parallel(get_context("spawn"))
    sink = TileSink(h.sink_descriptor(), lock)
    block = np.full((1, 10, 10), 5.0, dtype="float32")
    block[0, 0, 0] = NODATA_VALUE
    records = [sink.write_block((0, 0), block)]
    sink.close()

    # The nodata cell and the nodata value survive the round-trip
    h.collect_records(records)
    h.close()
    r = GeotiffReader(str(p))
    out = r[0].load()
    assert out[0, 0] == NODATA_VALUE
    assert out[1, 1] == 5.0
    assert r[0].nodata == NODATA_VALUE
    r.close()


def test_geotiff_writer_untouched_tiles_are_nodata(
    tmp_path: Path,
    hazard_event_data: NetcdfReader,
):
    # Write only one of the four tiles
    p = Path(tmp_path, "partial.tif")
    h = create_geotiff_handle(
        path=p,
        variables=["v"],
        ds_like=hazard_event_data,
        crs=hazard_event_data.profile.crs,
        tile=(5, 5),
    )
    lock = h.start_parallel(get_context("spawn"))
    sink = TileSink(h.sink_descriptor(), lock)
    block = np.full((1, 5, 5), 3.0, dtype="float32")
    records = [sink.write_block((0, 0), block)]
    sink.close()

    # The written tile holds its data; the untouched tiles come out as nodata
    h.collect_records(records)
    h.close()
    r = GeotiffReader(str(p))
    out = r[0].load()
    assert np.all(out[:5, :5] == 3.0)
    assert np.all(out[5:, :] == NODATA_VALUE)
    assert np.all(out[:, 5:] == NODATA_VALUE)
    r.close()
