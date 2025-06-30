from os import cpu_count
from pathlib import Path

import pytest

from fiat.cfg import Configurations
from fiat.fio import GridIO
from fiat.log import Logger
from fiat.models.base import BaseModel
from fiat.util import get_srs_repr

# Overwrite the abstractmethods to be able to initialize it
BaseModel.__abstractmethods__ = set()


def test_basemodel(config_empty: Configurations):
    # Create the object
    m = BaseModel(config_empty)

    # Assert some simple stuff
    # Data should be None still
    assert m.exposure_data is None
    assert m.exposure_geoms is None
    assert m.exposure_grid is None
    assert m.hazard_grid is None
    assert m.vulnerability_data is None


def test_basemodel_general_properties(config_empty: Configurations):
    # Create the object
    m = BaseModel(config_empty)

    # Assert the important properties
    assert not m.risk
    assert get_srs_repr(m.srs) == "EPSG:4326"
    assert m.threads == 1
    assert m.type == "flood"


def test_basemodel_risk(config_empty: Configurations):
    # Create the object
    m = BaseModel(config_empty)
    # Assert the current state
    assert not m.risk

    # Set the mode
    m.risk = True

    # Assert the state
    assert m.risk


def test_basemodel_threads(
    config_empty: Configurations,
):
    # Create the object
    m = BaseModel(config_empty)
    # Assert the current state
    assert m.threads == 1

    # This test is quite hazardous, let's just set the threads to zero to be able
    # To set it to 1
    m._threads = 0
    assert m.threads == 0
    # Set the threads
    m.threads = 1

    # Assert
    assert m.threads == 1


def test_basemodel_threads_warnings(
    config_empty: Configurations,
    caplog: Logger,
):
    # Create the object
    m = BaseModel(config_empty)
    # Assert the current state
    assert m.threads == 1

    # Pretty sure this exceeds any machine's cpu count
    m.threads = 1000

    # Assert the logging message
    assert (
        "Given number of threads ('1000') \
exceeds machine thread count"
        in caplog.text
    )
    assert m.threads == cpu_count()


def test_basemodel_type(config_empty: Configurations):
    # Create the object
    m = BaseModel(config_empty)
    # Assert the current state
    assert m.type == "flood"

    # This will error as there are no other modules
    with pytest.raises(
        ModuleNotFoundError,
        match="No module named 'fiat.methods.fatality'",
    ):
        m.type = "fatality"


def test_basemodel_read_hazard_config(
    hazard_event_path: Path,
    config_empty: Configurations,
):
    # Adjust the config
    config_empty.set("hazard.file", hazard_event_path)

    # Creat the object, which directly tries to read from the config
    m = BaseModel(config_empty)

    # Assert the state
    assert m.hazard_grid is not None
    assert isinstance(m.hazard_grid, GridIO)


def test_basemodel_read_hazard_argument(
    hazard_event_path: Path,
    config_empty: Configurations,
):
    # Creat the object, which directly tries to read from the config
    m = BaseModel(config_empty)
    # Assert the current state
    assert m.hazard_grid is None

    # Read with an argument
    m.read_hazard_grid(path=hazard_event_path)

    # Assert the state
    assert m.hazard_grid is not None
    assert isinstance(m.hazard_grid, GridIO)


def test_basemodel_read_hazard_risk(
    hazard_risk_path: Path,
    config_empty: Configurations,
):
    # Adjust the config
    config_empty.set("model.risk", True)
    config_empty.set("hazard.file", hazard_risk_path)
    config_empty.set("hazard.settings.var_as_band", True)

    # Creat the object, which directly tries to read from the config
    m = BaseModel(config_empty)

    # Assert the state
    assert m.hazard_grid is not None
    assert isinstance(m.hazard_grid, GridIO)
    assert m.cfg.get("hazard.return_periods") == [2.0, 5.0, 10.0, 25.0]


def test_basemodel_read_hazard_warnings(
    hazard_event_path: Path,
    config_empty: Configurations,
    caplog: Logger,
):
    # Adjust the config
    config_empty.set("model.srs.value", "EPSG:3857")
    config_empty.set("hazard.file", hazard_event_path)

    # Creat the object, which directly tries to read from the config
    m = BaseModel(config_empty)

    # Assert logging message
    assert "Setting the model srs from the hazard data." in caplog.text

    # Prefer global SRS over hazard SRS
    m.srs = "EPSG:3857"
    m.cfg.set("model.srs.prefer_global", True)

    # Re-read the hazard data
    m.read_hazard_grid()

    # Assert logging message
    assert (
        f"Spatial reference of '{hazard_event_path.name}' \
('EPSG:4326') does not match the \
model spatial reference ('EPSG:3857')"
        in caplog.text
    )
    assert Path(
        hazard_event_path.parent,
        f"{hazard_event_path.stem}_repr.tif",
    ).is_file()
