import pickle
from pathlib import Path

import numpy as np
import pytest
from osgeo import osr

from fiat.error import DriverNotFoundError
from fiat.fio.grid import GridIO
from fiat.util import get_srs_repr


def test_gridio_read_only(hazard_event_path: Path):
    # Open the dataset
    gio = GridIO(hazard_event_path)

    # Assert some simple stuff
    assert gio.mode == 0
    assert len(gio.bands) == 1
    # or
    assert gio.size == 1


def test_geomio_read_no_srs(
    hazard_event_no_srs_path: Path,
    srs: osr.SpatialReference,
):
    # Open a Dataset
    gio = GridIO(hazard_event_no_srs_path)

    # Assert some simple stuff
    assert gio.size == 1
    assert gio.src.GetSpatialRef() is None  # Verify that there is no srs
    assert gio.srs is None  # Cant induce from src and not set at GeomIO level

    # Close the dataset
    gio.close()

    # Open with srs as input argument to set the srs at GeomIO level
    gio = GridIO(hazard_event_no_srs_path, srs="EPSG:4326")

    # Assert the srs
    assert isinstance(gio.srs, osr.SpatialReference)
    assert get_srs_repr(gio.srs) == "EPSG:4326"
    assert gio.src.GetSpatialRef() is None  # Induces from layer still returns None

    # Or set directly
    gio._srs = None
    assert gio.srs is None
    gio.srs = srs

    # Assert the srs
    assert get_srs_repr(gio.srs) == "EPSG:4326"


def test_gridio_properties(hazard_event_path: Path):
    # Open the dataset
    gio = GridIO(hazard_event_path)

    # Assert that the properties return info and assert that the info is correct
    assert gio.band_names == ["Band1"]
    np.testing.assert_array_almost_equal(
        gio.bounds,
        [4.35, 4.45, 51.95, 52.05],
    )
    assert gio.dtype == 6
    assert gio.shape == (10, 10)
    assert gio.shape_xy == (10, 10)  # Shocker
    assert get_srs_repr(gio.srs) == "EPSG:4326"


def test_gridio_transform(tmp_path: Path):
    # Open the dataset
    gio = GridIO(Path(tmp_path, "tmp.tif"), mode="w")
    gio.create((10, 10), 1, 6)  # Create a dataset

    # Assert default geotransform
    np.testing.assert_array_almost_equal(
        gio.geotransform,
        (0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
    )

    # Create a new transform
    gtf = [1, 0.1, 0, 1, 0, -0.1]
    # Set the geotransform
    gio.geotransform = gtf

    # Assert the result
    np.testing.assert_almost_equal(gio.geotransform[1], 0.1)


def test_gridio_chunk(hazard_event_path: Path):
    # Open the dataset
    gio = GridIO(hazard_event_path)

    # Assert the current chunking
    assert gio.chunk == (10, 10)
    assert gio[0].chunk == (10, 10)

    # Set the chunking
    gio.chunk = (4, 4)
    assert gio.chunk == (4, 4)
    assert gio[0].chunk == (4, 4)


def test_gridio_chunk_error(hazard_event_path: Path):
    # Open the dataset
    gio = GridIO(hazard_event_path)

    # Assert error if not exactly two elements are passed
    with pytest.raises(
        ValueError,
        match="Chunk should have two elements",
    ):
        gio.chunk = (4, 4, 4)


def test_gridio_driver_error(tmp_path: Path):
    # Read a file extension that is not accepted
    with pytest.raises(
        DriverNotFoundError,
        match="Grid data -> \
Extension of file: tmp.unknown not recoqnized",
    ):
        _ = GridIO(Path(tmp_path, "tmp.unknown"), mode="w")


def test_gridio_state_error(hazard_event_path: Path):
    # Open the dataset
    gio = GridIO(hazard_event_path)

    # Should error when using a write only method
    with pytest.raises(ValueError, match="Invalid operation on a read-only file"):
        # Nonsense arguments are allowed, as this error kicks in before that
        # becomes a problem
        gio.create(None, None, None)

    # Get e.g. the geotransform
    assert len(gio.geotransform) == 6  # Affine
    # Now close the dataset
    gio.close()
    assert gio.src is None

    # Assert that asking for the geotransform now errors
    with pytest.raises(ValueError, match="Invalid operation on a closed file"):
        _ = gio.geotransform


def test_gridio_append(hazard_event_path: Path):
    # Open the dataset
    gio = GridIO(hazard_event_path, mode="a")

    # Assert some simple stuff
    assert gio.mode == 1
    # Even though we can write, there is data present due to append mode.
    assert len(gio.bands) == 1


def test_gridio_write(tmp_path: Path, srs: osr.SpatialReference):
    p = Path(tmp_path, "tmp.tif")  # Make a path
    # Open the dataset
    gio = GridIO(p, mode="w")

    # Assert the mode
    assert gio.mode == 2
    # assert gio.src is None

    # Create a source
    gio.create(
        shape=(7, 5),  # Not square
        nb=2,  # Two bands
        type=6,  # Float 32 bit
    )

    # Assert the information
    assert gio.shape == (5, 7)
    assert gio.shape_xy == (7, 5)  # har
    assert gio.dtype == 6
    assert gio.size == 2

    # Source srs is None
    assert gio.srs is None
    gio.set_source_srs(srs)

    # Assert the srs
    assert get_srs_repr(gio.srs) == "EPSG:4326"


def test_gridio_reopen(hazard_event_tmp_path: Path):
    # Open the dataset
    gio = GridIO(hazard_event_tmp_path, mode="a")

    # Reopen without closing should return same dataset
    obj = gio.reopen()
    assert id(gio) == id(obj)
    assert obj.mode == 1  # Still in append mode

    # Close the dataset and reopen
    gio.close()
    assert gio.src is None

    # Reopen the closed dataset
    obj = gio.reopen()
    assert id(obj) != id(gio)
    assert obj.mode == 0  # After reopening a closed dataset, it will be read mode
    assert obj.src is not None


def test_gridio_reduce(hazard_event_path: Path):
    # Open the dataset
    gio = GridIO(hazard_event_path)

    # Assert some simple stuff
    assert gio.size == 1

    # Reduce/ dump using pickle
    dump = pickle.dumps(gio)
    assert isinstance(dump, bytes)

    # Rebuild using pickle
    obj = pickle.loads(dump)
    # Number of bands should be the same
    assert obj.size == 1
