import shutil
from pathlib import Path
from typing import Callable, Generator

import netCDF4 as nc4
import numpy as np
import pytest

from fiat.driver import ConstantVariable, NetcdfReader
from fiat.error import FIATDataError
from fiat.log import Logger
from fiat.model import GridModel
from fiat.open import open_grid
from fiat.settings import GridSettings
from fiat.util import get_crs_repr


def test_gridmodel(model_settings: Callable[[str], GridSettings]):
    # Create the object
    m = GridModel(model_settings("grid_event.toml"))

    # Assert some simple stuff
    assert m.exposure is not None
    m.close()


def test_gridmodel_properties(model_settings: Callable[[str], GridSettings]):
    # Create the object
    m = GridModel(model_settings("grid_event.toml"))

    # Assert some simple stuff
    assert isinstance(m.exposure, NetcdfReader)
    m.close()


def test_gridmodel_read_exposure(model_settings: Callable[[str], GridSettings]):
    # Create the object
    m = GridModel(model_settings("grid_risk.toml"))

    # Assert nothing's there
    assert m.exposure is not None
    assert m.exposure.size == 2
    m.close()


def test_gridmodel_read_exposure_specs(model_settings: Callable[[str], GridSettings]):
    # Create the object, the settings define a uniform exposure layer
    m = GridModel(model_settings("grid_uniform.toml"))

    # Assert the state
    assert m.exposure.names == ["exposure1", "exposure2", "exposure3"]
    var = m.exposure.variables["exposure3"]
    assert isinstance(var, ConstantVariable)
    assert var.value == 1500.0
    assert var.get_attr("fn_curve") == "struct_1"
    m.close()

    # The settings override an attribute
    m = GridModel(model_settings("grid_override.toml"))
    assert m.exposure.variables["exposure1"].get_attr("fn_curve") == "struct_2"
    m.close()


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
    m.close()


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
    m.close()


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
    m.close()


def test_gridmodel_run_attribute_link(
    tmp_path: Path,
    exposure_grid_path: Path,
    model_settings: Callable[[str], GridSettings],
):
    # Copy of the exposure with a vulnerability link only set as an attribute
    p = Path(tmp_path, "spatial.nc")
    shutil.copy2(exposure_grid_path, p)
    with nc4.Dataset(p, "a") as ds:
        ds["exposure2"].setncattr("vulnerability", "default_2d")

    # Settings without any link to 'default_2d'
    settings = model_settings("grid_2d.toml")
    settings.update(
        output_dir=Path(tmp_path, "output"),
        exposure={
            "file": p.as_posix(),
            "vulnerability": "default",
            "settings": {"crs": "EPSG:4326"},
        },
    )
    m = GridModel(settings)
    m.run()
    m.close()

    # Assert the output, exposure2 (0, 1) via 'default_2d': depth 3.4, duration
    # 3.0 -> .96 (struct_2, capped) x .65
    with open_grid(settings.output.file) as reader:
        data = np.asarray(reader[reader.names.index("exposure2_1")].load())
    assert float(data[0, 1]) == pytest.approx(3100 * 0.96 * 0.65, rel=1e-5)


def test_gridmodel_run_level_error(
    model_settings: Callable[[str], GridSettings],
):
    # A method converting the hazard (water level) on a grid layer
    settings = model_settings("grid_event.toml")
    settings.update(
        vulnerability={
            "file": settings.vulnerability.file.as_posix(),
            "variables": [{"name": "default", "method": "flood.level"}],
        },
        hazard={
            "file": settings.hazard.file.as_posix(),
            "variables": [{"name": "data", "type": "water_level"}],
        },
    )
    m = GridModel(settings)

    # Assert the error before the run
    with pytest.raises(FIATDataError, match="flood.level"):
        m.run()
    m.close()
