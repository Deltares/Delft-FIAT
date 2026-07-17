import pickle
from pathlib import Path

import pytest
from osgeo import ogr
from pyproj.crs import CRS

from fiat.error import DriverNotFoundError
from fiat.fio.geom import GeomIO
from fiat.struct import GeomLayer
from fiat.util import get_crs_repr


def test_geomio_read_only(exposure_geom_path: Path):
    # Open a Dataset
    ds = GeomIO(exposure_geom_path)

    # Assert some simple stuff
    assert ds.mode == 0
    assert get_crs_repr(ds.crs) == "EPSG:4326"  # Induced from layer
    assert isinstance(ds.layer, GeomLayer)
    assert hash(ds) == hash(exposure_geom_path)


def test_geomio_read_no_crs(
    exposure_geom_no_crs_path: Path,
    crs_4326: CRS,
):
    # Open a Dataset
    ds = GeomIO(exposure_geom_no_crs_path)

    # Assert some simple stuff
    assert ds.layer.size == 4
    assert ds.layer.crs is None  # Verify that there is no crs
    assert ds.crs is None  # Cant induce from layer and not set at GeomIO level

    # Close the dataset
    ds.close()

    # Open with crs as input argument to set the crs at GeomIO level
    ds = GeomIO(exposure_geom_no_crs_path, crs="EPSG:4326")

    # Assert the crs
    assert isinstance(ds.crs, CRS)
    assert get_crs_repr(ds.crs) == "EPSG:4326"
    assert ds.layer.crs is None  # Induces from layer still returns None

    # Or set directly
    ds._crs = None
    assert ds.crs is None
    ds.crs = crs_4326

    # Assert the crs
    assert get_crs_repr(ds.crs) == "EPSG:4326"


def test_geomio_driver_error(tmp_path: Path):
    # Read a file extension that is not accepted
    with pytest.raises(
        DriverNotFoundError,
        match="Geometry data -> \
Extension of file: tmp.unknown not recoqnized",
    ):
        _ = GeomIO(Path(tmp_path, "tmp.unknown"), mode="w")


def test_geomio_read_error(tmp_path: Path):
    # Read something that does not exist
    p = Path(tmp_path, "tmp.geojson")
    with pytest.raises(
        FileNotFoundError,
        match=f"{p.as_posix()} doesn't exist, can't read",
    ):
        _ = GeomIO(p)


def test_geomio_state_errors(exposure_geom_path: Path):
    ds = GeomIO(exposure_geom_path)
    # Create e.g. a layer in read only mode
    with pytest.raises(ValueError, match="Invalid operation on a read-only file"):
        ds.create_layer(None, None)  # Doesn't matter that the args are bullshit

    # Close the dataset
    ds.close()

    # Assert that the layer cannot be requested
    with pytest.raises(ValueError, match="Invalid operation on a closed file"):
        _ = ds.layer


def test_geomio_append(exposure_geom_tmp_path: Path):
    # Open the dataset
    ds = GeomIO(exposure_geom_tmp_path, mode="a")

    # Assert some simple stuff
    assert ds.mode == 1
    # Even in write mode, it will already have a layer a its exists
    assert ds.layer is not None  # But no layer present
    assert ds.layer.size == 4


def test_geomio_delete(exposure_geom_tmp_path: Path):
    # Open the dataset
    ds = GeomIO(exposure_geom_tmp_path, mode="a")

    # Assert some simple stuff
    assert ds.src is not None
    assert ds.layer is not None
    assert ds.layer.size == 4

    # Delete the layer
    ds.delete(all=True)

    # Assert that its gone
    assert ds.src is None  # If src is None, layer cannot be requested


def test_geomio_write(tmp_path: Path, crs_4326: CRS):
    p = Path(tmp_path, "tmp.geojson")
    # Open the dataset
    ds = GeomIO(p, mode="w")

    # Assert some simple stuff
    assert ds.mode == 2
    # It will already have create a data source
    assert ds.src is not None
    assert ds.layer is None  # But no layer present

    # Create a layer
    ds.create_layer(crs_4326, geom_type=1)  # Point
    # Assert there is a layer
    assert ds.layer is not None
    assert ogr.GeometryTypeToName(ds.layer.geom_type) == "Point"


def test_geomio_write_overwrite(exposure_geom_tmp_path: Path):
    # Assert that the file exists
    assert exposure_geom_tmp_path.is_file()
    # Open the dataset
    ds = GeomIO(exposure_geom_tmp_path, mode="w", overwrite=True)

    # Assert some simple stuff
    assert ds.mode == 2
    # As the file is overwritten, the layer should be None
    assert ds.layer is None  # But no layer present


def test_geomio_reopen(exposure_geom_tmp_path: Path):
    # Open the dataset
    ds = GeomIO(exposure_geom_tmp_path, mode="a")

    # Reopen without closing should return same dataset
    obj = ds.reopen()
    assert id(ds) == id(obj)
    assert obj.mode == 1  # Still in append mode

    # Close the dataset and reopen
    ds.close()
    assert ds.src is None

    # Reopen the closed dataset
    obj = ds.reopen()
    assert id(obj) != id(ds)
    assert obj.mode == 0  # After reopening a closed dataset, it will be read mode
    assert obj.src is not None


def test_geomio_reduce(exposure_geom_path: Path):
    # Open the dataset
    ds = GeomIO(exposure_geom_path)

    # Assert some simple stuff
    assert ds.layer.size == 4

    # Reduce/ dump using pickle
    dump = pickle.dumps(ds)
    assert isinstance(dump, bytes)

    # Rebuild using pickle
    obj = pickle.loads(dump)
    # Size of the layer should be the same
    assert obj.layer.size == 4
