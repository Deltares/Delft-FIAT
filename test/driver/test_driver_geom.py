import pickle
from pathlib import Path

import numpy as np
import pytest
from pyproj.crs import CRS

from fiat.driver.fgb import Feature, FlatGeobufDriver, FlatLayer
from fiat.error import DriverNotFoundError
from fiat.util import get_crs_repr


def test_geomlayer(exposure_geom_data: FlatGeobufDriver):
    # Retrieve the geom layer from the I/O
    gl = exposure_geom_data.layer

    # Assert some simple stuff
    assert isinstance(gl, FlatLayer)
    assert gl.name == "spatial"
    assert gl.size == 4
    assert len(gl) == 4


def test_geomlayer_field_properties(exposure_geom_data: FlatGeobufDriver):
    # Retrieve the geom layer from the I/O
    gl = exposure_geom_data.layer

    # Assert the important attributes and properties
    assert gl.columns[:2] == ("object_id", "object_name")  # Field headers
    assert len(gl.columns) == 5
    # FlatGeobuf ColumnType codes: 5 = Int, 11 = String
    assert gl.dtypes[:2] == [5, 11]
    assert gl.fields[:2] == ["object_id", "object_name"]


def test_geomlayer_spatial_properties(exposure_geom_data: FlatGeobufDriver):
    # Retrieve the geom layer from the I/O
    gl = exposure_geom_data.layer

    # Assert the important attributes and properties
    np.testing.assert_array_almost_equal(
        gl.bounds,
        (0.5, 1.05, 8.95, 9.5),
    )
    assert gl.geom_type == 3  # i.e. 3 = Polygon
    assert get_crs_repr(gl.crs) == "EPSG:4326"


def test_geomlayer_iter(exposure_geom_data: FlatGeobufDriver):
    # Retrieve the geom layer from the I/O
    gl = exposure_geom_data.layer

    # Iterate over the layer
    idx = 0
    ft = None
    for ft in gl:
        idx += 1

    # Assert output
    assert isinstance(ft, Feature)
    assert idx == gl.size


def test_geomlayer_reduced_iter(exposure_geom_data: FlatGeobufDriver):
    # Retrieve the geom layer from the I/O
    gl = exposure_geom_data.layer

    # Iterate over the layer
    idx = 0
    for ft in gl.reduced_iter(1, 2):
        idx += 1

    # Assert the output
    assert idx == 2


def test_geomlayer_select_bbox(exposure_geom_data: FlatGeobufDriver):
    # Retrieve the geom layer from the I/O
    gl = exposure_geom_data.layer

    # Select features intersecting a bounding box using the R-tree
    feats = list(gl.select((0.0, 8.0, 2.0, 10.0)))

    # Assert the output: only the top-left polygon (object_id 1) is inside
    assert len(feats) == 1
    assert feats[0].get_field("object_id") == 1


def test_geomfeature_get_field(exposure_geom_data: FlatGeobufDriver):
    # Retrieve a feature
    ft = next(iter(exposure_geom_data.layer))

    # Access fields by index and by name
    assert ft.get_field(0) == ft.get_field("object_id")
    assert isinstance(ft.get_field("object_name"), str)
    assert ft[0] == ft.get_field(0)


def test_geomdriver_read_only(exposure_geom_path: Path):
    # Open a FlatGeobufDriver
    ds = FlatGeobufDriver(exposure_geom_path)

    # Assert some simple stuff
    assert ds.mode_str == "r"
    assert get_crs_repr(ds.crs) == "EPSG:4326"  # Induced from layer
    assert isinstance(ds.layer, FlatLayer)


def test_geomdriver_read_no_crs(
    exposure_geom_no_crs_path: Path,
    crs_4326: CRS,
):
    # Open a FlatGeobufDriver without a CRS
    ds = FlatGeobufDriver(exposure_geom_no_crs_path)

    # Assert some simple stuff
    assert ds.layer.size == 4
    assert ds.layer.crs is None  # Verify that there is no crs
    assert (
        ds.crs is None
    )  # Cant induce from layer and not set at FlatGeobufDriver level

    # Close the dataset
    ds.close()

    # Open with crs as input argument to set the crs at FlatGeobufDriver level
    ds = FlatGeobufDriver(exposure_geom_no_crs_path, crs="EPSG:4326")

    # Assert the crs
    assert isinstance(ds.crs, CRS)
    assert get_crs_repr(ds.crs) == "EPSG:4326"
    assert ds.layer.crs is None  # Inducing from layer still returns None


def test_geomdriver_driver_error(tmp_path: Path):
    # Read a file extension that is not accepted
    with pytest.raises(
        DriverNotFoundError,
        match="Geometry data -> \
Extension of file: tmp.unknown not recoqnized",
    ):
        _ = FlatGeobufDriver(Path(tmp_path, "tmp.unknown"), mode="w")


def test_geomdriver_read_error(tmp_path: Path):
    # Read something that does not exist
    p = Path(tmp_path, "tmp.fgb")
    with pytest.raises(
        FileNotFoundError,
        match=f"{p.as_posix()} doesn't exist, can't read",
    ):
        _ = FlatGeobufDriver(p)


def test_geomdriver_pickle(exposure_geom_path: Path):
    # Pickling should round-trip via __reduce__ (reopen by path)
    ds = FlatGeobufDriver(exposure_geom_path)
    ds2 = pickle.loads(pickle.dumps(ds))

    # Assert the reconstructed dataset works
    assert isinstance(ds2, FlatGeobufDriver)
    assert ds2.layer.size == 4


def test_geomdriver_reopen(exposure_geom_path: Path):
    # Open, close and reopen
    ds = FlatGeobufDriver(exposure_geom_path)
    ds.close()
    assert ds.closed is True

    ds = ds.reopen()
    assert ds.layer is not None
    assert ds.layer.size == 4


def test_geomdriver_write(tmp_path: Path):
    p = Path(tmp_path, "tmp.fgb")
    # Open the dataset in write mode
    ds = FlatGeobufDriver(p, mode="w")

    # Assert some simple stuff
    assert ds.mode_str == "w"
    assert ds.layer is None  # Nothing read in write mode


def test_geomdriver_write_overwrite(exposure_geom_tmp_path: Path):
    # Assert that the file exists
    assert exposure_geom_tmp_path.is_file()
    # Open the dataset in write mode
    ds = FlatGeobufDriver(exposure_geom_tmp_path, mode="w", overwrite=True)

    # Assert some simple stuff
    assert ds.mode_str == "w"
    assert ds.layer is None  # Write mode, nothing read
