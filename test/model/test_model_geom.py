from typing import Callable, Generator

import pytest

from fiat.container import Container
from fiat.driver import FlatGeobufReader
from fiat.log import Logger
from fiat.model import GeomModel
from fiat.settings import GeomSettings
from fiat.util import get_crs_repr


def test_geommodel(model_settings: Callable[[str], GeomSettings]):
    # Create the object
    m = GeomModel(model_settings("geom_event.toml"))

    # Assert some simple stuff
    assert isinstance(m.exposure, Container)


def test_geommodel_properties(model_settings: Callable[[str], GeomSettings]):
    # Create the object
    m = GeomModel(model_settings("geom_event.toml"))

    # Assert important properties/ attributes (one in this case :p)
    assert m.type == "geom"
    assert len(m.exposure) == 1
    assert isinstance(m.exposure.ds1.data, FlatGeobufReader)


def test_geommodel_read_exposure(model_settings: Callable[[str], GeomSettings]):
    # Create the object
    m = GeomModel(model_settings("geom_event.toml"))

    # Assert nothing's there
    assert len(m.exposure) == 1
    assert m.exposure.ds1.data.size == 4


def test_geommodel_read_exposure_multi(model_settings: Callable[[str], GeomSettings]):
    # Create the object
    m = GeomModel(model_settings("geom_event_2g.toml"))

    # Assert the presense of a dataset
    assert len(m.exposure) == 2
    assert m.exposure.ds1.data.profile.size == 4
    assert m.exposure.ds2.data.profile.size == 1


def test_geommodel_read_exposure_reproj(
    caplog: Logger,
    model_settings: Callable[[str], GeomSettings],
):
    # Create the object
    m = GeomModel(model_settings("geom_event.toml"))
    # Set the crs
    m.settings.projection.crs = "EPSG:3857"

    # Re-read it
    m._read_exposure()

    # Assert the logging
    assert "Reprojecting 'spatial.fgb' to 'EPSG:3857'" in caplog.text
    # Assert the dataset
    assert len(m.exposure) == 1
    assert m.exposure.ds1.data.profile.size == 4
    assert get_crs_repr(m.exposure.ds1.data.profile.crs) == "EPSG:3857"


def mockworker(*args, **kwargs):
    return None


def mockworker_error(*args, **kwargs):
    raise RuntimeError("No bueno...")


def test_geommodel_run(
    monkeypatch: Generator[pytest.MonkeyPatch, None, None],
    caplog: Logger,
    model_settings: Callable[[str], GeomSettings],
):
    # Monkeypatch the worker
    monkeypatch.setattr("fiat.model.geom.worker", mockworker)

    # Create the object
    m = GeomModel(model_settings("geom_event.toml"))
    m.threads = 1

    # Run the model
    m.run()

    # Assert logging
    assert "Running the model" in caplog.text
    assert "Busy..." in caplog.text
    assert "Model run is done!" in caplog.text


def test_geommodel_run_fail(
    monkeypatch: Generator[pytest.MonkeyPatch, None, None],
    caplog: Logger,
    model_settings: Callable[[str], GeomSettings],
):
    # Monkeypatch the worker
    monkeypatch.setattr("fiat.model.geom.worker", mockworker_error)

    # Create the object
    m = GeomModel(model_settings("geom_event.toml"))
    # Run the model
    m.run()

    # Assert logging
    assert "Running the model" in caplog.text
    assert "Busy..." in caplog.text
    assert "No bueno..." in caplog.text
    assert "Model run is done!" not in caplog.text
