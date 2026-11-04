from pathlib import Path
from typing import Any, Callable

import pytest
from pydantic import ValidationError

from fiat.log import Logger
from fiat.settings import (
    CURRENT_FORMAT_VERSION,
    BaseSettings,
    GeomSettings,
    GridSettings,
    load_settings,
)
from fiat.settings.exposure import ExposureGeometry, ExposureGrid
from fiat.settings.file import FileContext, InputFileModel
from fiat.settings.upgrade import SUPPORTED_UPGRADES, upgrade_to_latest
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


def test_settings_exposure_geom(testdata_dir: Path):
    # Setup the exposure with valid input
    _ = ExposureGeometry(
        file=Path(testdata_dir, "exposure", "spatial.fgb"),
        area_method="area",
        zonal_method="min",
    )

    _ = ExposureGeometry(
        file=Path(testdata_dir, "exposure", "spatial.fgb"),
        area_method="centroid",
        zonal_method="mean",
    )


def test_settings_exposure_geom_fail_area(testdata_dir: Path):
    # Setup the exposure with invalid area method
    with pytest.raises(
        ValidationError,
        match="1 validation error for ExposureGeometry\narea_method",
    ):
        _ = ExposureGeometry(
            file=Path(testdata_dir, "exposure", "spatial.fgb"), area_method="foo"
        )


def test_settings_exposure_geom_fail_zonal(testdata_dir: Path):
    # Setup the exposure with invalid zonal method
    with pytest.raises(
        ValidationError,
        match="1 validation error for ExposureGeometry\nzonal_method",
    ):
        _ = ExposureGeometry(
            file=Path(testdata_dir, "exposure", "spatial.fgb"), zonal_method="foo"
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


def test_settings_base_errors_loglevel(
    testdata_dir: Path,
    settings_dummy: dict[str, Any],
):
    settings_dummy["loglevel"] = "foo"
    # Load settings with an invalid log level
    with pytest.raises(
        ValidationError,
        match="Level \\(foo\\) is not a valid log level",
    ):
        _ = BaseSettings.model_validate(
            settings_dummy,
            context=FileContext(config_dir=testdata_dir),
        )


def test_settings_base_loglevel(testdata_dir: Path, settings_dummy: dict[str, Any]):
    settings_dummy["loglevel"] = "DEBUG"
    # Load settings
    settings = BaseSettings.model_validate(
        settings_dummy,
        context=FileContext(config_dir=testdata_dir),
    )

    # Assert simple stuff
    assert settings.loglevel == "DEBUG"


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


def test_settings_grid_output(testdata_dir: Path, settings_dummy: dict[str, Any]):
    settings_dummy["type"] = "grid"
    settings_dummy["exposure"] = {"file": "exposure/spatial.nc"}
    # Load settings without specifying an output file
    settings = GridSettings.model_validate(
        settings_dummy,
        context=FileContext(config_dir=testdata_dir),
    )

    # Assert the output file is derived from the exposure file
    assert settings.output.file.name == "spatial.tif"


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
def test_settings_base_format_version_current(
    testdata_dir: Path, settings_dummy: dict[str, Any]
):
    settings_dummy["format_version"] = CURRENT_FORMAT_VERSION
    settings = BaseSettings.model_validate(
        settings_dummy,
        context=FileContext(config_dir=testdata_dir),
    )
    assert settings.format_version == CURRENT_FORMAT_VERSION


def test_settings_base_format_version_missing(
    caplog: Logger, testdata_dir: Path, settings_dummy: dict[str, Any]
):
    settings_dummy.pop("format_version", None)
    settings = BaseSettings.model_validate(
        settings_dummy,
        context=FileContext(config_dir=testdata_dir),
    )

    # Treated as v0 and upgraded
    assert settings.format_version == CURRENT_FORMAT_VERSION
    assert "Format version not specified" in caplog.text
    assert "Format version 0 is deprecated" in caplog.text


def test_settings_base_format_version_v0_upgrade(
    caplog: Logger, testdata_dir: Path, settings_dummy: dict[str, Any]
):
    settings_dummy["format_version"] = 0
    settings = BaseSettings.model_validate(
        settings_dummy,
        context=FileContext(config_dir=testdata_dir),
    )

    assert settings.format_version == CURRENT_FORMAT_VERSION
    assert "Format version 0 is deprecated" in caplog.text
    assert "Format version not specified" not in caplog.text


def test_settings_base_format_version_input_not_mutated(
    testdata_dir: Path, settings_dummy: dict[str, Any]
):
    settings_dummy.pop("format_version", None)
    before = dict(settings_dummy)
    _ = BaseSettings.model_validate(
        settings_dummy,
        context=FileContext(config_dir=testdata_dir),
    )
    assert settings_dummy == before


@pytest.mark.parametrize("version", [-1, 99])
def test_settings_base_format_version_unsupported(
    testdata_dir: Path, settings_dummy: dict[str, Any], version: int
):
    settings_dummy["format_version"] = version
    with pytest.raises(
        ValidationError,
        match=f"Unsupported format version: {version}",
    ):
        _ = BaseSettings.model_validate(
            settings_dummy,
            context=FileContext(config_dir=testdata_dir),
        )


@pytest.mark.parametrize("version", ["1", 1.0, True])
def test_settings_base_format_version_wrong_type(
    testdata_dir: Path, settings_dummy: dict[str, Any], version: Any
):
    settings_dummy["format_version"] = version
    with pytest.raises(ValidationError, match="Unsupported format version"):
        _ = BaseSettings.model_validate(
            settings_dummy,
            context=FileContext(config_dir=testdata_dir),
        )


def test_settings_base_format_version_does_not_touch_threads(
    testdata_dir: Path, settings_dummy: dict[str, Any]
):
    # Regression: the validator was once attached to `threads` by mistake
    settings_dummy["threads"] = 2
    settings = BaseSettings.model_validate(
        settings_dummy,
        context=FileContext(config_dir=testdata_dir),
    )
    assert settings.threads == 2


def test_settings_base_format_version_to_dict(
    testdata_dir: Path, settings_dummy: dict[str, Any]
):
    settings = BaseSettings.model_validate(
        settings_dummy,
        context=FileContext(config_dir=testdata_dir),
    )
    assert settings.to_dict()["format_version"] == CURRENT_FORMAT_VERSION


def test_settings_base_format_version_update(
    testdata_dir: Path, settings_dummy: dict[str, Any]
):
    settings = BaseSettings.model_validate(
        settings_dummy,
        context=FileContext(config_dir=testdata_dir),
    )
    with pytest.raises(ValidationError, match="Unsupported format version: 99"):
        settings.update(format_version=99)


def test_upgrade_to_latest_noop():
    data = {"format_version": CURRENT_FORMAT_VERSION, "threads": 1}
    assert upgrade_to_latest(data) == data


def test_upgrade_to_latest_stuck(monkeypatch: pytest.MonkeyPatch):
    # An upgrade function that doesn't advance the version must not loop forever
    monkeypatch.setitem(SUPPORTED_UPGRADES, 0, lambda d: dict(d))
    with pytest.raises(RuntimeError, match="did not advance"):
        upgrade_to_latest({"format_version": 0})