import pickle
from pathlib import Path

import numpy as np
import pytest
from pyproj.crs import CRS

from fiat.driver.netcdf import NetcdfReader, NetcdfWriter
from fiat.util import get_crs_repr


def test_dataset(tmp_path: Path):
    # Open the dataset
    ds = NetcdfWriter(Path(tmp_path, "foo.nc"))

    # Assert some simple stuff
    assert ds.closed is False
    assert ds.size == 0


def test_dataset_read(hazard_event_path: Path):
    # Open the dataset
    ds = NetcdfReader(hazard_event_path)

    # Assert that the properties return info and assert that the info is correct
    np.testing.assert_array_almost_equal(
        ds.profile.bounds,
        [0.0, 0.0, 10.0, 10.0],
    )
    assert ds.variables["data"].dtype == np.float32
    assert ds.profile.shape == (10, 10)
    assert ds.profile.shape_xy == (10, 10)  # Shocker
    assert get_crs_repr(ds.profile.crs) == "EPSG:4326"


def test_dataset_read_crs(
    hazard_event_no_crs_path: Path,
    crs_4326: CRS,
):
    # Open a NetcdfReader
    ds = NetcdfReader(hazard_event_no_crs_path)

    # Assert some simple stuff
    assert ds.size == 1
    assert ds.reference is None  # Verify that there is no crs
    assert ds.profile.crs is None  # Cant induce from src and not set at reader level

    # Close the dataset
    ds.close()

    # Open with crs as input argument to set the crs at reader level
    ds = NetcdfReader(hazard_event_no_crs_path, crs="EPSG:4326")

    # Assert the crs
    assert isinstance(ds.profile.crs, CRS)
    assert get_crs_repr(ds.profile.crs) == "EPSG:4326"
    assert ds.reference is None  # Induces from layer still returns None

    # Or set directly on the profile
    ds.profile.crs_wkt = None
    assert ds.profile.crs is None
    ds.profile.crs_wkt = crs_4326.to_wkt()

    # Assert the crs
    assert get_crs_repr(ds.profile.crs) == "EPSG:4326"


def test_dataset_read_transform(hazard_event_path: Path):
    # Open the dataset
    ds = NetcdfReader(hazard_event_path)

    # Assert default geotransform
    np.testing.assert_array_almost_equal(
        ds.profile.transform,
        (0.0, 1.0, 0.0, 10.0, 0.0, -1.0),
    )


def test_dataset_lazy_window(hazard_event_path: Path):
    # Open the dataset
    ds = NetcdfReader(hazard_event_path)
    band = ds.variables["data"]

    # A windowed read returns only that window
    window = (slice(0, 5), slice(0, 5))
    data = band.read_window(window)
    assert data.shape == (5, 5)

    # Hold a window in memory and have it served from the cache
    held = band.read_window(window, hold=True)
    np.testing.assert_array_equal(band[window], held)

    # Clearing the held window falls back to reading from disk
    band.clear_window()
    np.testing.assert_array_equal(band[window], held)


def test_dataset_state_error(hazard_event_path: Path):
    # Open the dataset
    ds = NetcdfReader(hazard_event_path)

    # The read driver has no write methods (reader/writer are now separate)
    assert not hasattr(ds, "create_spatial_dims")

    # Get e.g. the geotransform
    assert len(ds.profile.transform) == 6  # Affine
    # Now close the dataset
    ds.close()

    # Assert that asking for the size now errors
    with pytest.raises(ValueError, match="Invalid operation on a closed file"):
        _ = ds.size


def test_dataset_write(tmp_path: Path, crs_4326: CRS):
    p = Path(tmp_path, "foo.nc")  # Make a path
    # Open the dataset
    ds = NetcdfWriter(p)

    # Assert the state
    assert ds.closed is False

    # Create the dimensions
    ds.create_spatial_dims(
        lats=np.arange(0.5, 2.6, 0.5),
        lons=np.arange(0.5, 3.6, 0.5),
    )

    # Assert the information
    assert ds.profile.shape == (5, 7)
    assert ds.profile.shape_xy == (7, 5)  # har
    assert ds.size == 0

    # Source crs is None
    assert ds.profile.crs is None
    ds.set_spatial_ref(crs_4326)

    # Assert the crs
    assert get_crs_repr(ds.profile.crs) == "EPSG:4326"
    # Close and assert the file is present
    ds.close()
    assert p.is_file()


def test_dataset_reduce(hazard_event_path: Path):
    # Open the dataset
    ds = NetcdfReader(hazard_event_path)

    # Assert some simple stuff
    assert ds.size == 1

    # Reduce/ dump using pickle
    dump = pickle.dumps(ds)
    assert isinstance(dump, bytes)

    # Rebuild using pickle
    obj = pickle.loads(dump)
    # Number of bands should be the same
    assert obj.size == 1
