import pickle
from pathlib import Path

import numpy as np
import pytest
from pyproj.crs import CRS

from fiat.fio.netcdf import Dataset
from fiat.util import get_crs_repr


def test_dataset(tmp_path: Path):
    # Open the dataset
    ds = Dataset(Path(tmp_path, "foo.nc"), "w")

    # Assert some simple stuff
    assert ds.mode == 2
    assert ds.size == 0


def test_dataset_read(hazard_event_path: Path):
    # Open the dataset
    ds = Dataset(hazard_event_path)

    # Assert that the properties return info and assert that the info is correct
    # assert ds.variables == [None]
    np.testing.assert_array_almost_equal(
        ds.bounds,
        [0.0, 0.0, 10.0, 10.0],
    )
    assert ds.variables["data"].dtype == np.float32
    assert ds.shape == (10, 10)
    assert ds.shape_xy == (10, 10)  # Shocker
    assert get_crs_repr(ds.crs) == "EPSG:4326"


def test_dataset_read_crs(
    hazard_event_no_crs_path: Path,
    crs_4326: CRS,
):
    # Open a Dataset
    ds = Dataset(hazard_event_no_crs_path)

    # Assert some simple stuff
    assert ds.size == 1
    assert ds.reference is None  # Verify that there is no crs
    assert ds.crs is None  # Cant induce from src and not set at GeomIO level

    # Close the dataset
    ds.close()

    # Open with crs as input argument to set the crs at GeomIO level
    ds = Dataset(hazard_event_no_crs_path, crs="EPSG:4326")

    # Assert the crs
    assert isinstance(ds.crs, CRS)
    assert get_crs_repr(ds.crs) == "EPSG:4326"
    assert ds.reference is None  # Induces from layer still returns None

    # Or set directly
    ds._crs = None
    assert ds.crs is None
    ds._crs = crs_4326.to_wkt()

    # Assert the crs
    assert get_crs_repr(ds.crs) == "EPSG:4326"


def test_dataset_read_transform(hazard_event_path: Path):
    # Open the dataset
    ds = Dataset(hazard_event_path, mode="r")

    # Assert default geotransform
    np.testing.assert_array_almost_equal(
        ds.transform,
        (0.0, 1.0, 0.0, 10.0, 0.0, -1.0),
    )


def test_dataset_state_error(hazard_event_path: Path):
    # Open the dataset
    ds = Dataset(hazard_event_path)

    # Should error when using a write only method
    with pytest.raises(ValueError, match="Invalid operation on a read-only file"):
        # Nonsense arguments are allowed, as this error kicks in before that
        # becomes a problem
        ds.create_spatial_dims(None, None)

    # Get e.g. the geotransform
    assert len(ds.transform) == 6  # Affine
    # Now close the dataset
    ds.close()

    # Assert that asking for the shape now errors
    with pytest.raises(ValueError, match="Invalid operation on a closed file"):
        _ = ds.shape


def test_dataset_append(hazard_event_path: Path):
    # Open the dataset
    ds = Dataset(hazard_event_path, mode="a")

    # Assert some simple stuff
    assert ds.mode == 1
    # Even though we can write, there is data present due to append mode.
    assert len(ds.variables) == 1


def test_dataset_write(tmp_path: Path, crs_4326: CRS):
    p = Path(tmp_path, "foo.nc")  # Make a path
    # Open the dataset
    ds = Dataset(p, mode="w")

    # Assert the mode
    assert ds.mode == 2
    # assert ds.src is None

    # Create the dimensions
    ds.create_spatial_dims(
        lats=np.arange(0.5, 2.6, 0.5),
        lons=np.arange(0.5, 3.6, 0.5),
    )

    # Assert the information
    assert ds.shape == (5, 7)
    assert ds.shape_xy == (7, 5)  # har
    assert ds.size == 0

    # Source crs is None
    assert ds.crs is None
    ds.set_spatial_ref(crs_4326)

    # Assert the crs
    assert get_crs_repr(ds.crs) == "EPSG:4326"
    # Close and assert the file is present
    ds.close()
    assert p.is_file()


def test_dataset_reduce(hazard_event_path: Path):
    # Open the dataset
    ds = Dataset(hazard_event_path)

    # Assert some simple stuff
    assert ds.size == 1

    # Reduce/ dump using pickle
    dump = pickle.dumps(ds)
    assert isinstance(dump, bytes)

    # Rebuild using pickle
    obj = pickle.loads(dump)
    # Number of bands should be the same
    assert obj.size == 1
