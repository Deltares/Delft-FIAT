from typing import Callable, Generator

import pytest

from fiat.driver import NetcdfReader
from fiat.log import Logger
from fiat.model import GridModel
from fiat.settings import GridSettings
from fiat.util import get_crs_repr


def test_gridmodel(model_settings: Callable[[str], GridSettings]):
    # Create the object
    m = GridModel(model_settings("grid_event.toml"))

    # Assert some simple stuff
    assert m.exposure is not None


def test_gridmodel_properties(model_settings: Callable[[str], GridSettings]):
    # Create the object
    m = GridModel(model_settings("grid_event.toml"))

    # Assert some simple stuff
    assert isinstance(m.exposure, NetcdfReader)


def test_gridmodel_read_exposure(model_settings: Callable[[str], GridSettings]):
    # Create the object
    m = GridModel(model_settings("grid_risk.toml"))

    # Assert nothing's there
    assert m.exposure is not None
    assert m.exposure.size == 2


def test_gridmodel_read_exposure_reproj(
    caplog: Logger,
    model_settings: Callable[[str], GridSettings],
):
    # Create the object
    m = GridModel(model_settings("grid_event.toml"))
    # Set the model crs
    m.crs = "EPSG:3857"

    # Re-call the method
    m._read_exposure()

    # Assert the logging
    assert "Reprojecting 'spatial.nc' to 'EPSG:3857'" in caplog.text
    # Assert the dataset
    assert isinstance(m.exposure, NetcdfReader)
    assert m.exposure.size == 2
    assert get_crs_repr(m.exposure.profile.crs) == "EPSG:3857"


def mockworker(*args, **kwargs):
    return None


def mockworker_error(*args, **kwargs):
    raise RuntimeError("No bueno...")


def test_gridmodel_run(
    monkeypatch: Generator[pytest.MonkeyPatch, None, None],
    caplog: Logger,
    model_settings: Callable[[str], GridSettings],
):
    # Monkeypatch the worker
    monkeypatch.setattr("fiat.model.grid.worker", mockworker)

    # Create the object
    m = GridModel(model_settings("grid_event.toml"))
    m.threads = 1

    # Run the model
    m.run()

    # Assert logging
    assert "Running the model" in caplog.text
    assert "Busy..." in caplog.text
    assert "Model run is done!" in caplog.text


def test_gridmodel_run_fail(
    monkeypatch: Generator[pytest.MonkeyPatch, None, None],
    caplog: Logger,
    model_settings: Callable[[str], GridSettings],
):
    # Monkeypatch the worker
    monkeypatch.setattr("fiat.model.grid.worker", mockworker_error)

    # Create the object
    m = GridModel(model_settings("grid_event.toml"))

    # Run the model
    m.run()

    # Assert logging
    assert "Running the model" in caplog.text
    assert "Busy..." in caplog.text
    assert "No bueno..." in caplog.text
    assert "Model run is done!" not in caplog.text
