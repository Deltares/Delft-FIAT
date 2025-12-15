from fiat.cfg import Configurations
from fiat.models import GeomModel
from fiat.struct import Container


def test_geommodel(config_empty: Configurations):
    # Create the object
    m = GeomModel(config_empty)

    # Assert some simple stuff
    assert isinstance(m.exposure, Container)
    assert len(m.exposure) == 0


def test_geommodel_properties(config_empty: Configurations):
    # Create the object
    m = GeomModel(config_empty)

    # Assert important properties/ attributes (one in this case :p)
    assert m.exposure_types == ["damage"]


def test_geommodel_read_exposure(config_empty: Configurations):
    # Create the object
    m = GeomModel(config_empty)

    # Call the method
    m.read_exposure()

    # Assert nothing's there
    assert len(m.exposure) == 0
