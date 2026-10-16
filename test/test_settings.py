from pathlib import Path
from typing import Any, Callable

import pytest
from pydantic import ValidationError

from fiat.log import Logger
from fiat.settings import BaseSettings, GeomSettings, GridSettings, load_settings
from fiat.settings.exposure import ExposureGrid
from fiat.settings.file import FileContext, InputFileModel
from fiat.util import FLOOD_DEPTH


def test_settings_input_file(testdata_dir: Path):
    # Assert validation of an existing file
    InputFileModel.model_validate(
        {"file": Path(testdata_dir, "exposure", "spatial.fgb")},
    )


def test_settings_input_file_errors(tmp_path: Path):
    # Assert error on a non existing file
    with pytest.raises(
        ValidationError,
        match="1 validation error for InputFileModel",
    ):
        InputFileModel.model_validate(
            {"file", Path(tmp_path, "foo.fgb")},
        )


def test_settings_base(testdata_dir: Path, settings_dummy: dict[str, Any]):
    # Load settings
    settings = BaseSettings.model_validate(
        settings_dummy,
        context=FileContext(config_dir=testdata_dir),
    )

    # Assert simple stuff
    assert settings.threads == 1
    assert settings.hazard.file.is_file()
    assert settings.vulnerability.file.is_file()
    assert settings.output_dir == Path(testdata_dir, "output")


def test_settings_base_warnings(
    caplog: Logger, testdata_dir: Path, settings_dummy: dict[str, Any]
):
    settings_dummy["threads"] = 1000
    # Load settings
    _ = BaseSettings.model_validate(
        settings_dummy,
        context=FileContext(config_dir=testdata_dir),
    )

    # Assert simple stuff
    assert "Given number of threads ('1000')" in caplog.text


def test_settings_base_errors(testdata_dir: Path, settings_dummy: dict[str, Any]):
    settings_dummy["threads"] = -1
    # Load settings with invalid number of threads (negative)
    with pytest.raises(
        ValidationError,
        match="1 validation error for BaseSettings",
    ):
        _ = BaseSettings.model_validate(
            settings_dummy,
            context=FileContext(config_dir=testdata_dir),
        )


def test_settings_base_to_dict(testdata_dir: Path, settings_dummy: dict[str, Any]):
    # Load settings
    settings = BaseSettings.model_validate(
        settings_dummy,
        context=FileContext(config_dir=testdata_dir),
    )

    # Dump to dictionary
    settings_dict = settings.to_dict()
    # Assert the output
    assert settings_dict["output_dir"] == "output"
    assert settings_dict["threads"] == 1
    assert settings_dict["hazard"]["file"] == "event_map.nc"


def test_settings_base_update(testdata_dir: Path, settings_dummy: dict[str, Any]):
    # Load settings
    settings = BaseSettings.model_validate(
        settings_dummy,
        context=FileContext(config_dir=testdata_dir),
    )
    # Assert settings
    assert settings.threads == 1

    # Update
    settings.update(threads=4)
    # Assert settings
    assert settings.threads == 4


def test_settings_base_from_toml(settings_files: Callable[[str], Path]):
    # Load settings
    settings = BaseSettings.from_toml(settings_files("geom_event.toml"))
    # Assert settings
    assert settings.threads == 1
    assert settings.hazard.file.is_file()


def test_settings_load_settings_geom(settings_files: Callable[[str], Path]):
    # Call the function
    settings = load_settings(
        settings_files("geom_event.toml"),
    )

    # Assert type
    assert isinstance(settings, GeomSettings)

    # Assert some content
    assert settings.type == "geom"
    assert isinstance(settings.exposure, list)
    assert settings.method == FLOOD_DEPTH


def test_settings_load_settings_grid(settings_files: Callable[[str], Path]):
    # Call the function
    settings = load_settings(
        settings_files("grid_event.toml"),
    )

    # Assert type
    assert isinstance(settings, GridSettings)

    # Assert some content
    assert settings.type == "grid"
    assert isinstance(settings.exposure, ExposureGrid)
    assert settings.method == FLOOD_DEPTH


def test_settings_load_settings_error(tmp_path: Path):
    # Call with nonsense path
    with pytest.raises(
        FileNotFoundError,
        match=f"{Path(tmp_path, 'foo.toml').as_posix()} is not a valid file",
    ):
        _ = load_settings(filename=Path(tmp_path, "foo.toml"))
