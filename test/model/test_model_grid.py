from fiat.cfg import Configurations
from fiat.model import GridModel


def test_gridmodel(config_empty: Configurations):
    # Create the object
    m = GridModel(config_empty)

    # Assert some simple stuff
    assert m.exposure is None


def test_gridmodel_read_exposure(config_empty: Configurations):
    # Create the object
    m = GridModel(config_empty)

    # Call the method
    m.read_exposure()

    # Assert nothing's there
    assert m.exposure is None
