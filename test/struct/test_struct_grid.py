import numpy as np
import pytest
from osgeo import gdal

from fiat.fio import GridIO
from fiat.struct.grid import GridBand


def test_gridband(hazard_event_data: GridIO):
    # Retrieve the grid band from the I/O
    gb = hazard_event_data[0]

    # Assert some simple stuff
    assert isinstance(gb._obj, gdal.Band)
    assert id(gb.ref) == id(hazard_event_data.src)
    assert gb.mode == hazard_event_data.mode


def test_gridband_init_error():
    # Should error as normal init is not supported
    with pytest.raises(
        AttributeError,
        match="No constructer defined",
    ):
        _ = GridBand()


def test_gridband_general_properties(hazard_event_data: GridIO):
    # Retrieve the grid band from the I/O
    gb = hazard_event_data[0]

    # Assert important properties/ attributes
    assert gb.description == ""
    assert gb.dtype == 6
    assert gb.dtype_name == "Float32"
    assert gb.index == ()
    assert gb.kwargs == {}
    assert gb.meta["NETCDF_VARNAME"] == "Band1"
    assert gb.nodata == 9.969209968386869e36  # Awful number


def test_gridband_spatial_properties(hazard_event_data: GridIO):
    # Retrieve the grid band from the I/O
    gb = hazard_event_data[0]

    # Assert important properties/ attributes
    assert gb.chunk == (10, 10)  # Not set so same as the grid size
    assert gb.shape == (10, 10)
    assert gb.shape_xy == (10, 10)  # Grid is square.. will test also lateri


def test_gridband_chunk(hazard_event_data: GridIO):
    # Retrieve the grid band from the I/O
    gb = hazard_event_data[0]
    # Assert the current chunking
    assert gb.chunk == (10, 10)

    # Set new chunking
    gb.chunk = (5, 5)

    # Assert the new chunking
    assert gb.chunk == (5, 5)


def test_gridband_chunk_errors(hazard_event_data: GridIO):
    # Retrieve the grid band from the I/O
    gb = hazard_event_data[0]

    # Assert that chunking can only have two elemets
    with pytest.raises(
        ValueError,
        match="Chunk should have two elements",
    ):
        gb.chunk = (5, 5, 5)


def test_gridband_iter(hazard_event_data: GridIO):
    # Retrieve the grid band from the I/O
    gb = hazard_event_data[0]
    # Set some new, uneven chunking
    gb.chunk = (4, 4)

    idx = 0
    # Go through the windows
    for window, chunk in gb:
        if idx == 0:
            first_window, first_chunk = window, chunk
        idx += 1

    # Assert the output
    assert idx == 9
    assert first_chunk.shape == (4, 4)
    assert first_window == (0, 0, 4, 4)
    assert chunk.shape == (2, 2)  # Bottom remaining corner
    assert window == (8, 8, 2, 2)


def test_gridband_get_metadata_item(hazard_event_data: GridIO):
    # Retrieve the grid band from the I/O
    gb = hazard_event_data[0]

    # Call the method
    assert gb.get_metadata_item("NETCDF_VARNAME") == "Band1"
    assert gb.get_metadata_item("foo") == "None"  # Gdal stuff...


def test_gridband_write_chunk(hazard_write: GridIO):
    # Retrieve the grid band from the I/O
    gb = hazard_write[0]
    # Assert the current state of the data
    np.testing.assert_array_equal(
        gb[0, 0, 2, 3],
        np.array([[0, 0], [0, 0], [0, 0]]),
    )

    # Write a chunk to the band
    gb.write_chunk(np.array([[2, 2], [2, 2]]), (0, 0))

    # Assert the output
    np.testing.assert_array_equal(
        gb[0, 0, 2, 3],
        np.array([[2, 2], [2, 2], [0, 0]]),
    )
