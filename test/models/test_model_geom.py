from pathlib import Path

from fiat.cfg import Configurations
from fiat.fio import GeomIO, GridIO
from fiat.models import GeomModel, worker_geom
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


def test_geommodel_read_exposure_sig(
    config_empty: Configurations, exposure_geom_path: Path
):
    # Create the object
    m = GeomModel(config_empty)

    # Call the method
    m.read_exposure(path=exposure_geom_path)

    # Assert the presense of a dataset
    assert len(m.exposure) == 1


def mockworker(*args, **kwargs):
    raise ValueError()
    return None


def test_geommodel_run(
    monkeypatch,
    config_empty: Configurations,
    hazard_event_data: GridIO,
    exposure_geom_dataset: GeomIO,
):
    monkeypatch.setattr(worker_geom, "worker", mockworker)

    # Create the object
    m = GeomModel(config_empty)
    m.hazard = hazard_event_data
    m.exposure.set(exposure_geom_dataset)

    # Run the model
    m.run()
