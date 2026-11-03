from pathlib import Path
from typing import Callable

import pytest

from fiat.driver import ConstantVariable, NetcdfReader
from fiat.error import FIATDataError
from fiat.log import Logger
from fiat.model.base import BaseModel
from fiat.open import open_grid
from fiat.settings import GeomSettings, GridSettings
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
    assert isinstance(m.vulnerability, NetcdfReader)
    m.close()


def test_basemodel_general_properties(model_settings: Callable[[str], GeomSettings]):
    # Create the object
    m = BaseModel(model_settings("geom_event.toml"))

    # Assert the important properties
    assert not m.risk
    assert get_crs_repr(m.crs) == "EPSG:4326"
    assert m.threads == 1
    assert m.type == "geom"
    assert not hasattr(m, "method")
    m.close()


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
    m.close()


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
    m.close()


def test_basemodel_read_hazard(model_settings: Callable[[str], GeomSettings]):
    # Creat the object, which directly tries to read from the config
    m = BaseModel(model_settings("geom_event.toml"))

    # Assert the state
    assert m.hazard is not None
    assert isinstance(m.hazard, NetcdfReader)
    assert m.hazard.size == 1
    m.close()


def test_basemodel_read_hazard_specs(model_settings: Callable[[str], GridSettings]):
    # Create the object, the settings define a uniform duration layer
    m = BaseModel(model_settings("grid_uniform.toml"))

    # Assert the state
    assert m.hazard.names == ["data", "duration"]
    assert isinstance(m.hazard.variables["duration"], ConstantVariable)
    assert m.hazard.variables["duration"].get_attr("type") == "duration"
    m.close()


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
    m.close()


def test_basemodel_read_vulnerability(model_settings: Callable[[str], GeomSettings]):
    # Create the object
    m = BaseModel(model_settings("geom_event.toml"))

    # Assert the state
    assert m.vulnerability is not None
    assert isinstance(m.vulnerability, NetcdfReader)
    assert m.vulnerability.names == ["default"]
    m.close()


def test_basemodel_read_vulnerability_specs(
    model_settings: Callable[[str], GridSettings],
):
    # Create the object, the settings override the method and the axis types
    m = BaseModel(model_settings("grid_override.toml"))

    # Assert the state
    var = m.vulnerability.variables["default_2d"]
    assert var.get_attr("method") == "flood.depth_duration_2d"
    assert var.get_attr("types") == {
        "depth_default_2d": "water_depth",
        "duration_default_2d": "duration",
    }
    m.close()


def test_basemodel_close(model_settings: Callable[[str], GeomSettings]):
    # Create the object
    m = BaseModel(model_settings("geom_event.toml"))

    # Close the data, twice is fine
    m.close()
    m.close()

    # Assert the state
    assert m.hazard.closed
    assert m.vulnerability.closed


def test_basemodel_missing_variable(
    monkeypatch: pytest.MonkeyPatch,
    model_settings: Callable[[str], GridSettings],
):
    # Keep track of the opened data
    opened = []

    def _open_grid(*args, **kwargs):
        opened.append(open_grid(*args, **kwargs))
        return opened[-1]

    monkeypatch.setattr("fiat.model.base.open_grid", _open_grid)

    # A hazard variable not in the file
    with pytest.raises(FIATDataError, match="nope"):
        BaseModel(model_settings("grid_missing_variable.toml"))

    # Assert the vulnerability data that had been read is closed
    assert len(opened) == 1
    assert opened[0].closed
