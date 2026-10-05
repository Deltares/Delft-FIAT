import os
from multiprocessing import get_context
from multiprocessing.shared_memory import SharedMemory
from pathlib import Path

import numpy as np

from fiat.driver import NetcdfReader, NetcdfWriter
from fiat.util import NODATA_VALUE
from fiat.writer import GridItem, GridOutputWriter, create_netcdf_handle


def test_create_netcdf_handle(
    tmp_path: Path,
    hazard_event_data: NetcdfReader,
):
    # Creat the handle
    h = create_netcdf_handle(
        path=Path(tmp_path, "foo.nc"),
        variables=["data"],
        ds_like=hazard_event_data,
    )

    # Assert the output
    assert Path(tmp_path, "foo.nc").is_file()
    assert h.profile.shape == (10, 10)
    assert h.size == 1


def test_create_netcdf_handle_overwrite(
    tmp_path: Path,
    hazard_event_data: NetcdfReader,
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
    h = create_netcdf_handle(
        path=Path(tmp_path, "foo.nc"),
        variables=["data"],
        ds_like=hazard_event_data,
    )

    # Assert the output
    assert Path(tmp_path, "foo.nc").is_file()
    assert os.stat(p).st_size > 0
    assert h.profile.shape == (10, 10)
    assert h.size == 1


def test_netcdf_writer(
    dummy_queue: type,
):
    # Create the writer
    w = GridOutputWriter(
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


def test_netcdf_writer_setup(
    dummy_queue: type,
    grid_handle: NetcdfWriter,
):
    # Create the writer
    w = GridOutputWriter(
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

    # Cleanup
    w.close()


def test_netcdf_writer_close(
    dummy_queue: type,
    grid_handle: NetcdfWriter,
):
    # Create the writer
    w = GridOutputWriter(
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


def test_netcdf_writer_fn(
    dummy_queue: type,
    grid_handle: NetcdfWriter,
):
    # Create the writer
    w = GridOutputWriter(
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
    ds = NetcdfReader(w.handle.path)
    np.testing.assert_array_equal(
        ds[0][slice(0, 2), slice(0, 2)],
        np.array([[2, 2], [2, 2]]),
    )


def test_grid_item():
    # Set the signalling struct
    item = GridItem(mem_id="block-1", origin=(1, 2), shape=(3, 4))

    # Assert the fields and equality
    assert item.mem_id == "block-1"
    assert item.origin == (1, 2)
    assert item.shape == (3, 4)
    assert item == GridItem(mem_id="block-1", origin=(1, 2), shape=(3, 4))


def test_create_netcdf_handle_multiple(
    tmp_path: Path,
    hazard_event_data: NetcdfReader,
):
    # Creat the handle with two variables
    h = create_netcdf_handle(
        path=Path(tmp_path, "foo.nc"),
        variables=["depth", "damage"],
        ds_like=hazard_event_data,
    )

    # Assert the output
    assert Path(tmp_path, "foo.nc").is_file()
    assert h.profile.shape == (10, 10)
    assert h.size == 2
    assert h.names == ["depth", "damage"]


def test_netcdf_writer_fn_nodata(
    dummy_queue: type,
    grid_handle: NetcdfWriter,
):
    # Create the writer
    w = GridOutputWriter(
        queue=dummy_queue,
        handle=grid_handle,
        ctx=get_context("spawn"),
    )

    # Set data like a dummy, with a nan in it
    w.locks["foo"] = w.ctx.Lock()
    w.mem_locs["foo"] = SharedMemory("foo", create=True, size=16)
    w.mem_blocks["foo"] = np.ndarray(
        shape=(1, 2, 2),
        dtype=np.float32,
        buffer=w.mem_locs["foo"].buf,
    )
    w.mem_blocks["foo"][:] = np.array([[[1, np.nan], [3, 4]]], dtype=np.float32)
    w.piperecv["foo"], w.pipesend["foo"] = w.ctx.Pipe(duplex=False)

    # Execute the main method
    w.fn(
        record=GridItem(mem_id="foo", origin=(0, 0), shape=(10, 10)),
    )

    # Assert the block was reset to nan after writing
    assert np.isnan(w.mem_blocks["foo"]).all()
    w.close()

    # Assert nan was written as the nodata value
    ds = NetcdfReader(w.handle.path)
    np.testing.assert_array_equal(
        ds[0][slice(0, 2), slice(0, 2)],
        np.array([[1, NODATA_VALUE], [3, 4]], dtype=np.float32),
    )
