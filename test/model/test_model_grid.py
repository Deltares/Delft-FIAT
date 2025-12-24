from pathlib import Path
from typing import Generator

import pytest
from osgeo import osr

from fiat.cfg import Configurations
from fiat.fio import GridIO
from fiat.log import Logger
from fiat.model import GridModel
from fiat.struct import Table
from fiat.util import get_srs_repr


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


def test_gridmodel_read_exposure_config(
    config_read_grid: Configurations,
):
    # Create the object
    m = GridModel(config_read_grid)

    # Call the method
    m.read_exposure()

    # Assert the presense of a dataset
    assert isinstance(m.exposure, GridIO)
    assert m.exposure.size == 2


def test_gridmodel_read_exposure_sig(
    config_empty: Configurations,
    exposure_grid_path: Path,
):
    # Create the object
    m = GridModel(config_empty)

    # Call the method
    m.read_exposure(path=exposure_grid_path, var_as_band=True)

    # Assert the presense of a dataset
    assert isinstance(m.exposure, GridIO)
    assert m.exposure.size == 2


def test_gridmodel_read_exposure_reproj(
    caplog: Logger,
    config_empty: Configurations,
    srs_3857: osr.SpatialReference,
    exposure_grid_path: Path,
):
    # Create the object
    m = GridModel(config_empty)
    m._srs = srs_3857

    # Call the method
    m.read_exposure(path=exposure_grid_path, var_as_band=True)

    # Assert the logging
    assert "Reprojecting 'spatial.nc' to 'EPSG:3857'" in caplog.text
    # Assert the dataset
    assert isinstance(m.exposure, GridIO)
    assert m.exposure.size == 2
    assert get_srs_repr(m.exposure.srs) == "EPSG:3857"


def mockworker(*args, **kwargs):
    return None


def mockworker_error(*args, **kwargs):
    raise RuntimeError("No bueno...")


def test_gridmodel_run(
    monkeypatch: Generator[pytest.MonkeyPatch, None, None],
    caplog: Logger,
    config_empty: Configurations,
    vulnerability_data_run: Table,
    hazard_event_data: GridIO,
    exposure_grid_data: GridIO,
):
    # Monkeypatch the worker
    monkeypatch.setattr("fiat.model.grid.worker", mockworker)

    # Create the object
    m = GridModel(config_empty)
    m.threads = 2
    # Set data like a dummy
    m.vulnerability = vulnerability_data_run
    m.hazard = hazard_event_data
    m.exposure = exposure_grid_data

    # Run the model
    m.run()

    # Assert logging
    assert "Running the model" in caplog.text
    assert "Busy..." in caplog.text
    assert "Model run is done!" in caplog.text


def test_gridmodel_run_fail(
    monkeypatch: Generator[pytest.MonkeyPatch, None, None],
    caplog: Logger,
    config_empty: Configurations,
    vulnerability_data_run: Table,
    hazard_event_data: GridIO,
    exposure_grid_data: GridIO,
):
    # Monkeypatch the worker
    monkeypatch.setattr("fiat.model.grid.worker", mockworker_error)

    # Create the object
    m = GridModel(config_empty)
    # Set data like a dummy
    m.vulnerability = vulnerability_data_run
    m.hazard = hazard_event_data
    m.exposure = exposure_grid_data

    # Run the model
    m.run()

    # Assert logging
    assert "Running the model" in caplog.text
    assert "Busy..." in caplog.text
    assert "No bueno..." in caplog.text
    assert "Model run is done!" not in caplog.text


def test_geommodel_run_errors(
    config_empty: Configurations,
):
    # Create the object
    m = GridModel(config_empty)

    # Should error on having no data
    with pytest.raises(
        TypeError,
        match="hazard is incorrectly set, currently of type NoneType",
    ):
        m.run()
