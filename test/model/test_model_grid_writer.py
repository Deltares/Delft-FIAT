import os
from multiprocessing import get_context
from multiprocessing.shared_memory import SharedMemory
from pathlib import Path

import numpy as np
from osgeo import osr

from fiat.fio import GridIO
from fiat.model.grid_writer import GridItem, GridWriter, create_grid_handle


def test_create_grid_handle(
    tmp_path: Path,
    srs_4326: osr.SpatialReference,
):
    # Creat the handle
    h = create_grid_handle(
        path=Path(tmp_path, "foo.nc"),
        shape=(10, 10),
        nb=1,
        srs=srs_4326,
        gtf=(0.0, 1.0, 0.0, 10.0, 0.0, -1.0),
    )

    # Assert the output
    assert Path(tmp_path, "foo.nc").is_file()
    assert h.shape == (10, 10)
    assert len(h.bands) == 1


def test_create_grid_handle_overwrite(
    tmp_path: Path,
    srs_4326: osr.SpatialReference,
):
    p = Path(tmp_path, "foo.nc")
    # Assert current state
    assert not p.is_file()

    # Touch the file
    p.touch()
    # Assert it's there
    assert p.is_file()
    assert os.stat(p).st_size == 0

    # Creat the handle
    h = create_grid_handle(
        path=p,
        shape=(10, 10),
        nb=1,
        srs=srs_4326,
        gtf=(0.0, 1.0, 0.0, 10.0, 0.0, -1.0),
    )

    # Assert the output
    assert Path(tmp_path, "foo.nc").is_file()
    assert os.stat(p).st_size > 0
    assert h.shape == (10, 10)
    assert len(h.bands) == 1


def test_grid_writer(
    dummy_queue: type,
):
    # Create the writer
    w = GridWriter(
        queue=dummy_queue,
        handle=None,
        ctx=None,
    )

    # Assert some basic stuff
    assert not w.closed
    assert w.count == 0
    assert w.thread is None
    assert w.locks == {}
    assert w.mem_blocks == {}
    assert w.mem_locs == {}
    assert w.piperecv == {}
    assert w.pipesend == {}


def test_grid_writer_setup(
    dummy_queue: type,
    grid_handle: GridIO,
):
    # Create the writer
    w = GridWriter(
        queue=dummy_queue,
        handle=grid_handle,
        ctx=get_context("spawn"),
    )

    # Call the method to setup a block of memory
    w.setup_block(
        mem_id="test-block",
        shape=(10, 10),
    )

    # Assert the state
    assert "test-block" in w.locks
    assert "test-block" in w.mem_blocks
    assert w.mem_blocks["test-block"].shape == (1, 10, 10)
    assert "test-block" in w.mem_locs
    assert "test-block" in w.piperecv
    assert "test-block" in w.pipesend


def test_grid_writer_close(
    dummy_queue: type,
    grid_handle: GridIO,
):
    # Create the writer
    w = GridWriter(
        queue=dummy_queue,
        handle=grid_handle,
        ctx=get_context("spawn"),
    )

    # Set data like a dummy
    w.locks["foo"] = w.ctx.Lock()
    w.mem_locs["foo"] = SharedMemory("foo", create=True, size=16)
    w.mem_blocks["foo"] = np.ndarray(
        shape=(1, 2, 2),
        dtype=np.float32,
        buffer=w.mem_locs["foo"].buf,
    )
    w.piperecv["foo"], w.pipesend["foo"] = w.ctx.Pipe(duplex=False)

    # Shut it down
    w.close()

    # Assert the state
    assert w.closed == True
    assert "foo" not in w.locks
    assert "foo" not in w.mem_blocks
    assert "foo" not in w.mem_locs
    assert "foo" not in w.piperecv
    assert "foo" not in w.pipesend


def test_grid_writer_fn(
    dummy_queue: type,
    grid_handle: GridIO,
):
    # Create the writer
    w = GridWriter(
        queue=dummy_queue,
        handle=grid_handle,
        ctx=get_context("spawn"),
    )

    # Set data like a dummy
    w.locks["foo"] = w.ctx.Lock()
    w.mem_locs["foo"] = SharedMemory("foo", create=True, size=16)
    w.mem_blocks["foo"] = np.ndarray(
        shape=(1, 2, 2),
        dtype=np.float32,
        buffer=w.mem_locs["foo"].buf,
    )
    w.mem_blocks["foo"][:] = 2
    w.piperecv["foo"], w.pipesend["foo"] = w.ctx.Pipe(duplex=False)

    # Execute the main method
    w.fn(
        record=GridItem(mem_id="foo", origin=(0, 0), shape=(10, 10)),
    )
    w.close()

    # Assert the output
    ds = GridIO(w.handle.path)
    np.testing.assert_array_equal(
        ds[0][0, 0, 2, 2],
        np.array([[2, 2], [2, 2]]),
    )
