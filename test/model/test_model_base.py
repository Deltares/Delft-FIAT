from pathlib import Path
from typing import Callable

from fiat.driver import NetcdfReader, Table
from fiat.log import Logger
from fiat.model.base import BaseModel
from fiat.settings import GeomSettings
from fiat.util import get_crs_repr

# Overwrite the abstractmethods to be able to initialize it
BaseModel.__abstractmethods__ = set()


def test_basemodel(model_settings: Callable[[str], GeomSettings]):
    # Create the object
    m = BaseModel(model_settings("geom_event.toml"))

    # Assert some simple stuff
    # Data should be None still
    assert m.hazard is not None
    assert m.vulnerability is not None
    assert isinstance(m.hazard, NetcdfReader)
    assert isinstance(m.vulnerability, Table)


def test_basemodel_general_properties(model_settings: Callable[[str], GeomSettings]):
    # Create the object
    m = BaseModel(model_settings("geom_event.toml"))

    # Assert the important properties
    assert not m.risk
    assert get_crs_repr(m.crs) == "EPSG:4326"
    assert m.threads == 1
    assert m.type == "geom"
    assert m.settings.method == "flood.depth"


def test_basemodel_risk(model_settings: Callable[[str], GeomSettings]):
    # Create the object
    m = BaseModel(model_settings("geom_event.toml"))
    # Assert the current state
    assert not m.risk

    # Set the mode
    m.risk = True

    # Assert the state
    assert m.risk
    assert m.settings.risk


def test_basemodel_threads(model_settings: Callable[[str], GeomSettings]):
    # Create the object
    m = BaseModel(model_settings("geom_event.toml"))
    # Assert the current state
    assert m.threads == 1

    # Set the threads
    m.threads = 2

    # Assert
    assert m.threads == 2
    assert m.settings.threads == 2


def test_basemodel_read_hazard(model_settings: Callable[[str], GeomSettings]):
    # Creat the object, which directly tries to read from the config
    m = BaseModel(model_settings("geom_event.toml"))

    # Assert the state
    assert m.hazard is not None
    assert isinstance(m.hazard, NetcdfReader)
    assert m.hazard.size == 1


def test_basemodel_read_hazard_warnings(
    model_settings: Callable[[str], GeomSettings],
    caplog: Logger,
):
    # Creat the object, which directly tries to read from the config
    m = BaseModel(model_settings("geom_event.toml"))
    # Set the projection
    m.crs = "EPSG:3857"

    # Assert logging message
    assert "Setting the model crs from the hazard data." in caplog.text

    # Prefer global SRS over hazard SRS
    m.crs = "EPSG:3857"
    m.settings.projection.force = True

    # Re-read the hazard data
    m._read_hazard()

    # Assert logging message
    assert (
        f"Spatial reference of '{m.settings.hazard.file.name}' \
('EPSG:4326') does not match the \
model spatial reference ('EPSG:3857')"
        in caplog.text
    )
    assert Path(
        m.settings.hazard.file.parent,
        f"{m.settings.hazard.file.stem}_repr.nc",
    ).is_file()


def test_basemodel_read_vulnerability(model_settings: Callable[[str], GeomSettings]):
    # Create the object
    m = BaseModel(model_settings("geom_event.toml"))

    # Assert the state
    assert m.vulnerability is not None
    assert isinstance(m.vulnerability, Table)
    # Had been upscaled so a long index
    assert len(m.vulnerability.index) == 21
