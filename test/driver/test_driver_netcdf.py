import pickle
from pathlib import Path

import numpy as np
import pytest
from pyproj.crs import CRS

from fiat.driver.netcdf import NetcdfReader, NetcdfWriter
from fiat.util import get_crs_repr


def test_netcdf(tmp_path: Path):
    # Open the dataset
    ds = NetcdfWriter(Path(tmp_path, "foo.nc"))

    # Assert some simple stuff
    assert ds.closed is False
    assert ds.size == 0


def test_netcdf_read(hazard_event_path: Path):
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


def test_netcdf_read_crs(
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


def test_netcdf_read_transform(hazard_event_path: Path):
    # Open the dataset
    ds = NetcdfReader(hazard_event_path)

    # Assert default geotransform
    np.testing.assert_array_almost_equal(
        ds.profile.transform,
        (0.0, 1.0, 0.0, 10.0, 0.0, -1.0),
    )


def test_netcdf_load(hazard_event_path: Path):
    # Open the dataset
    ds = NetcdfReader(hazard_event_path)
    band = ds.variables["data"]

    # A windowed read returns only that window
    window = slice(0, 5), slice(0, 5)
    data = band.load(*window)
    assert data.shape == (5, 5)

    # Hold a window in memory and have it served from the cache
    held = band.load(*window)
    np.testing.assert_array_equal(band[*window], held)


def test_netcdf_state_error(hazard_event_path: Path):
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


def test_netcdf_write(tmp_path: Path, crs_4326: CRS):
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


def test_netcdf_write_window(tmp_path: Path, crs_4326: CRS):
    # write_window mirrors the GeoTIFF API and fans out across variables
    p = Path(tmp_path, "win.nc")
    ds = NetcdfWriter(p, compression="zlib", complevel=4)
    lats = np.arange(0.5, 4.5, 1.0)  # 4 rows
    lons = np.arange(0.5, 5.5, 1.0)  # 5 cols
    ds.create_spatial_dims(lats=lats, lons=lons)
    ds.set_spatial_ref(crs_4326)
    ds.create_spatial_variable("a")
    ds.create_spatial_variable("b")

    # Two bands written as one (bands, h, w) window
    ny, nx = len(lats), len(lons)
    data = np.stack(
        [np.arange(ny * nx, dtype="f4").reshape(ny, nx), np.ones((ny, nx), "f4")]
    )
    ds.write_window((0, 0), data)
    ds.close()

    with NetcdfReader(p) as r:
        np.testing.assert_array_equal(r.variables["a"].load(), data[0])
        np.testing.assert_array_equal(r.variables["b"].load(), data[1])


def test_netcdf_reduce(hazard_event_path: Path):
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
