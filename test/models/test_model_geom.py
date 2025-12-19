from pathlib import Path
from typing import Generator

import pytest
from osgeo import osr

from fiat.cfg import Configurations
from fiat.fio import GeomIO, GridIO
from fiat.log import Logger
from fiat.models import GeomModel
from fiat.struct import Container, Table
from fiat.util import get_srs_repr


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


def test_geommodel_read_exposure_config(
    config_read_geom: Configurations,
):
    # Create the object
    m = GeomModel(config_read_geom)

    # Call the method
    m.read_exposure()

    # Assert the presense of a dataset
    assert len(m.exposure) == 2
    assert m.exposure.ds1.layer.size == 4
    assert m.exposure.ds2.layer.size == 1


def test_geommodel_read_exposure_sig(
    config_empty: Configurations,
    exposure_geom_path: Path,
):
    # Create the object
    m = GeomModel(config_empty)

    # Call the method
    m.read_exposure(path=exposure_geom_path)

    # Assert the presense of a dataset
    assert len(m.exposure) == 1
    assert m.exposure.ds1.layer.size == 4


def test_geommodel_read_exposure_reproj(
    caplog: Logger,
    config_empty: Configurations,
    srs_3857: osr.SpatialReference,
    exposure_geom_path: Path,
):
    # Create the object
    m = GeomModel(config_empty)
    m._srs = srs_3857

    # Call the method
    m.read_exposure(path=exposure_geom_path)

    # Assert the logging
    assert "Reprojecting 'spatial.geojson' to 'EPSG:3857'" in caplog.text
    # Assert the dataset
    assert len(m.exposure) == 1
    assert m.exposure.ds1.layer.size == 4
    assert get_srs_repr(m.exposure.ds1.srs) == "EPSG:3857"


def mockworker(*args, **kwargs):
    return None


def mockworker_error(*args, **kwargs):
    raise RuntimeError("No bueno...")


def test_geommodel_run(
    monkeypatch: Generator[pytest.MonkeyPatch],
    caplog: Logger,
    config_empty: Configurations,
    vulnerability_data_run: Table,
    hazard_event_data: GridIO,
    exposure_geom_dataset: GeomIO,
):
    # Monkeypatch the worker
    monkeypatch.setattr("fiat.models.geom.worker", mockworker)

    # Create the object
    m = GeomModel(config_empty)
    m.threads = 2
    # Set data like a dummy
    m.vulnerability = vulnerability_data_run
    m.hazard = hazard_event_data
    m.exposure.set(exposure_geom_dataset)

    # Run the model
    m.run()

    # Assert logging
    assert "Running the model" in caplog.text
    assert "Busy..." in caplog.text
    assert "Model run is done!" in caplog.text


def test_geommodel_run_fail(
    monkeypatch,
    caplog: Logger,
    config_empty: Configurations,
    vulnerability_data_run: Table,
    hazard_event_data: GridIO,
    exposure_geom_dataset: GeomIO,
):
    # Monkeypatch the worker
    monkeypatch.setattr("fiat.models.geom.worker", mockworker_error)

    # Create the object
    m = GeomModel(config_empty)
    # Set data like a dummy
    m.vulnerability = vulnerability_data_run
    m.hazard = hazard_event_data
    m.exposure.set(exposure_geom_dataset)

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
    m = GeomModel(config_empty)

    # Should error on having no data
    with pytest.raises(
        TypeError,
        match="hazard is incorrectly set, currently of type NoneType",
    ):
        m.run()
