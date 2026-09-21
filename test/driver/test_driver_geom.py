import pickle
from pathlib import Path

import numpy as np
import pytest
from osgeo import ogr
from pyproj.crs import CRS

from fiat.driver.geom import GeomIO, GeomLayer
from fiat.error import DriverNotFoundError
from fiat.util import get_crs_repr


def test_geomlayer(exposure_geom_data: GeomIO):
    # Retrieve the geom layer from the I/O
    gl = exposure_geom_data.layer

    # Assert some simple stuff
    assert isinstance(gl._obj, ogr.Layer)
    assert id(gl.ref) == id(exposure_geom_data.src)
    assert gl.mode == exposure_geom_data.mode


def test_geomlayer_init_error():
    # Should error as normal init is not supported
    with pytest.raises(
        AttributeError,
        match="No constructer defined",
    ):
        _ = GeomLayer()


def test_geomlayer_general_properties(exposure_geom_data: GeomIO):
    # Retrieve the geom layer from the I/O
    gl = exposure_geom_data.layer

    # Assert the important attributes and properties
    assert gl.index == ()
    assert gl.index_name == "index"
    assert gl.kwargs == {}
    assert gl.name == "spatial"
    assert gl.size == 4


def test_geomlayer_field_properties(exposure_geom_data: GeomIO):
    # Retrieve the geom layer from the I/O
    gl = exposure_geom_data.layer

    # Assert the important attributes and properties
    assert gl.columns[:2] == ("object_id", "object_name")  # Field headers
    assert len(gl.columns) == 5
    assert gl.dtypes[:2] == [0, 4]  # i.e. int and string
    assert gl.fields[:2] == ["object_id", "object_name"]  # Field headers
    assert isinstance(gl.defn, ogr.FeatureDefn)


def test_geomlayer_spatial_properties(exposure_geom_data: GeomIO):
    # Retrieve the geom layer from the I/O
    gl = exposure_geom_data.layer

    # Assert the important attributes and properties
    np.testing.assert_array_almost_equal(
        gl.bounds,
        (0.5, 1.05, 8.95, 9.5),
    )
    assert gl.geom_type == 3  # i.e. 3 = Polygon
    assert get_crs_repr(gl.crs) == "EPSG:4326"


def test_geomlayer_iter(exposure_geom_data: GeomIO):
    # Retrieve the geom layer from the I/O
    gl = exposure_geom_data.layer

    # Iterate over the layer
    idx = 0
    for ft in gl:
        idx += 1

    # Assert output
    assert isinstance(ft, ogr.Feature)
    assert idx == gl.size


def test_geomlayer_reduced_iter(exposure_geom_data: GeomIO):
    # Retrieve the geom layer from the I/O
    gl = exposure_geom_data.layer

    # Iterate over the layer
    idx = 0
    for ft in gl.reduced_iter(1, 2):
        idx += 1

    # Assert the output
    assert idx == 2


def test_geomlayer_add_feature(exposure_geom_write: GeomIO):
    # Retrieve the geom layer from the I/O
    gl = exposure_geom_write.layer
    # Assert the current state
    assert gl.size == 0

    # Create a dummy feature
    geom = ogr.Geometry(ogr.wkbPoint)
    geom.AddPoint_2D(1, 1)
    ft = ogr.Feature(gl.defn)
    ft.SetGeometry(geom)
    ft.SetFID(1)

    # Add the feature
    gl.add_feature(ft)

    # Assert the output
    assert gl.size == 1


def test_geomlayer_add_feature_with_map(
    exposure_geom_write: GeomIO,
    feature: ogr.Feature,
):
    # Retrieve the geom layer from the I/O
    gl = exposure_geom_write.layer
    # Assert the current state
    assert gl.size == 0

    # Add extra field for testing
    gl.create_field("foo", 2)

    # Add the feature by calling method with map
    gl.add_feature_with_map(feature, zip(["foo"], [2.2]))

    # Depends on gpkg driver though
    assert gl.size == 1
    assert gl[0].GetField(0) == 2.2


def test_geomlayer_create_field(exposure_geom_write: GeomIO):
    # Retrieve the geom layer from the I/O
    gl = exposure_geom_write.layer
    # Assert the current state
    assert gl.fields == []
    assert gl.dtypes == []

    # Create a field
    gl.create_field("foo", 2)  # 2 is floating point data

    # Assert the state after
    assert gl.fields == ["foo"]
    assert gl.dtypes == [2]


def test_geomlayer_create_fields(exposure_geom_write: GeomIO):
    # Retrieve the geom layer from the I/O
    gl = exposure_geom_write.layer
    # Assert the current state
    assert gl.fields == []
    assert gl.dtypes == []

    # Create multiple fields at once
    gl.create_fields({"foo": 2, "bar": 0})  # 2 is float, 0 is int

    # Assert the state after
    assert gl.fields == ["foo", "bar"]
    assert gl.dtypes == [2, 0]


def test_geomlayer_set_from_defn(exposure_geom_write: GeomIO):
    # Retrieve the geom layer from the I/O
    gl = exposure_geom_write.layer
    # Assert the current state
    assert gl.fields == []
    assert gl.dtypes == []

    # Create a dummy layer definition
    defn = ogr.FeatureDefn()
    defn.SetGeomType(ogr.wkbPoint)
    defn.AddFieldDefn(ogr.FieldDefn("foo", 2))
    defn.AddFieldDefn(ogr.FieldDefn("bar", 0))

    # Set the layer defn from another defn
    gl.set_from_defn(defn)

    # Assert the state after
    assert gl.fields == ["foo", "bar"]
    assert gl.dtypes == [2, 0]


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
