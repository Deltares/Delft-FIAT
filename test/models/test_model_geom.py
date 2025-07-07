from fiat.cfg import Configurations
from fiat.models import GeomModel


def test_geommodel(config_empty: Configurations):
    # Create the object
    m = GeomModel(config_empty)

    # Assert some simple stuff
    assert m.exposure_data == {}
    assert m.exposure_geoms == {}


def test_geommodel_properties(config_empty: Configurations):
    # Create the object
    m = GeomModel(config_empty)

    # Assert important properties/ attributes (one in this case :p)
    assert m.exposure_types == ["damage"]
