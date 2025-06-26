import numpy as np
import pytest
from osgeo import ogr

from fiat.fio import GeomIO
from fiat.struct.geom import GeomLayer
from fiat.util import get_srs_repr


def test_geomlayer(exposure_geom_dataset: GeomIO):
    # Retrieve the geom layer from the I/O
    gl = exposure_geom_dataset.layer

    # Assert some simple stuff
    assert isinstance(gl._obj, ogr.Layer)
    assert id(gl.ref) == id(exposure_geom_dataset.src)
    assert gl.mode == exposure_geom_dataset.mode


def test_geomlayer_init_error():
    # Should error as normal init is not supported
    with pytest.raises(
        AttributeError,
        match="No constructer defined",
    ):
        _ = GeomLayer()


def test_geomlayer_general_properties(exposure_geom_dataset: GeomIO):
    # Retrieve the geom layer from the I/O
    gl = exposure_geom_dataset.layer

    # Assert the important attributes and properties
    assert gl.index == ()
    assert gl.index_name == "index"
    assert gl.kwargs == {}
    assert gl.name == "spatial"
    assert gl.size == 4


def test_geomlayer_field_properties(exposure_geom_dataset: GeomIO):
    # Retrieve the geom layer from the I/O
    gl = exposure_geom_dataset.layer

    # Assert the important attributes and properties
    assert gl.columns == ("object_id", "object_name")  # Field headers
    assert gl.dtypes == [0, 4]  # i.e. int and string
    assert gl.fields == ["object_id", "object_name"]  # Field headers
    assert isinstance(gl.defn, ogr.FeatureDefn)


def test_geomlayer_spatial_properties(exposure_geom_dataset: GeomIO):
    # Retrieve the geom layer from the I/O
    gl = exposure_geom_dataset.layer

    # Assert the important attributes and properties
    np.testing.assert_array_almost_equal(
        gl.bounds,
        (0.5, 8.95, 1.05, 9.5),
    )
    assert gl.geom_type == 3  # i.e. 3 = Polygon
    assert get_srs_repr(gl.srs) == "EPSG:4326"


def test_geomlayer_iter(exposure_geom_dataset: GeomIO):
    # Retrieve the geom layer from the I/O
    gl = exposure_geom_dataset.layer

    # Iterate over the layer
    idx = 0
    for ft in gl:
        idx += 1

    # Assert output
    assert isinstance(ft, ogr.Feature)
    assert idx == gl.size


def test_geomlayer_reduced_iter(exposure_geom_dataset: GeomIO):
    # Retrieve the geom layer from the I/O
    gl = exposure_geom_dataset.layer

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
