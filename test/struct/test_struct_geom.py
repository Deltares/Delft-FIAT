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
    np.testing.assert_array_almost_equal(
        gl.bounds,
        (4.355, 4.4395, 51.9605, 52.045),
    )
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
        (4.355, 4.4395, 51.9605, 52.045),
    )
    assert gl.geom_type == 3  # i.e. 3 = Polygon
    assert get_srs_repr(gl.srs) == "EPSG:4326"
