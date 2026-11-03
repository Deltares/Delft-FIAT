from pathlib import Path
from typing import Any, Callable

import pytest
from pydantic import ValidationError

from fiat.log import Logger
from fiat.settings import BaseSettings, GeomSettings, GridSettings, load_settings
from fiat.settings.exposure import ExposureGeometry, ExposureGrid
from fiat.settings.file import FileContext, InputFileModel
from fiat.settings.hazard import Hazard
from fiat.settings.variables import (
    ExposureGridVariable,
    HazardVariable,
    VulnerabilityVariable,
)
from fiat.settings.vulnerability import Vulnerability


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
        vulnerability="default",
    )

    _ = ExposureGeometry(
        file=Path(testdata_dir, "exposure", "spatial.fgb"),
        area_method="centroid",
        zonal_method="mean",
        vulnerability="default",
    )


def test_settings_exposure_geom_vulnerability_required(testdata_dir: Path):
    # The link to the vulnerability dataset is required
    with pytest.raises(ValidationError, match="vulnerability"):
        _ = ExposureGeometry(file=Path(testdata_dir, "exposure", "spatial.fgb"))


def test_settings_exposure_geom_fail_area(testdata_dir: Path):
    # Setup the exposure with invalid area method
    with pytest.raises(
        ValidationError,
        match="1 validation error for ExposureGeometry\narea_method",
    ):
        _ = ExposureGeometry(
            file=Path(testdata_dir, "exposure", "spatial.fgb"),
            area_method="foo",
            vulnerability="default",
        )


def test_settings_exposure_geom_fail_zonal(testdata_dir: Path):
    # Setup the exposure with invalid zonal method
    with pytest.raises(
        ValidationError,
        match="1 validation error for ExposureGeometry\nzonal_method",
    ):
        _ = ExposureGeometry(
            file=Path(testdata_dir, "exposure", "spatial.fgb"),
            zonal_method="foo",
            vulnerability="default",
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
    settings_dummy["exposure"] = {
        "file": "exposure/spatial.nc",
        "variables": [
            {
                "name": "exposure1",
                "type": "default",
                "fn_curve": "struct_1",
                "vulnerability": "default",
            }
        ],
    }
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
    assert not hasattr(settings, "method")


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
    assert not hasattr(settings, "method")


def test_settings_load_settings_error(tmp_path: Path):
    # Call with nonsense path
    with pytest.raises(
        FileNotFoundError,
        match=f"{Path(tmp_path, 'foo.toml').as_posix()} is not a valid file",
    ):
        _ = load_settings(filename=Path(tmp_path, "foo.toml"))


def test_settings_variables_parse(settings_files: Callable[[str], Path]):
    # Load settings with variables entries
    settings = load_settings(settings_files("grid_multi_combined.toml"))

    # Assert the content
    assert isinstance(settings.exposure.variables[1], ExposureGridVariable)
    assert settings.exposure.variables[1].vulnerability == ["direct", "indirect"]
    assert not hasattr(settings, "method")


def test_settings_vulnerability_value_forbidden(vulnerability_path: Path):
    # Assert value is not allowed on vulnerability variables
    with pytest.raises(ValidationError, match="value"):
        Vulnerability.model_validate(
            {"file": vulnerability_path, "variables": [{"name": "a", "value": 1}]}
        )


def test_settings_exposure_variable_value_values():
    # Uniform categorized layer
    var = ExposureGridVariable(
        name="landuse", type="categorized", value=1, values=["values"]
    )
    assert var.values == ["values"]
    assert var.value == 1

    # Values on a non categorized layer
    with pytest.raises(ValidationError, match="values"):
        ExposureGridVariable(name="foo", type="default", values=["values"])

    # Unknown type
    with pytest.raises(ValidationError, match="type"):
        ExposureGridVariable(name="foo", type="other")


def test_settings_variable_required_fields(hazard_event_path: Path):
    # A hazard variable needs a type
    with pytest.raises(ValidationError, match="type"):
        HazardVariable(name="data")

    # A vulnerability variable needs a method and types
    with pytest.raises(ValidationError, match="method"):
        VulnerabilityVariable(name="default", types={"depth_default": "water_depth"})
    with pytest.raises(ValidationError, match="types"):
        VulnerabilityVariable(name="default", method="flood.depth")

    # A default exposure layer needs a curve id
    with pytest.raises(ValidationError, match="fn_curve"):
        ExposureGridVariable(name="exposure1", type="default", vulnerability="default")

    # The variables are as set
    hazard = Hazard(
        file=hazard_event_path,
        variables=[
            HazardVariable(name="d", type="duration", rp=10, value=3.0),
            HazardVariable(name="data", type="water_depth"),
        ],
    )
    assert hazard.variables[0].rp == 10
    assert hazard.variables[0].value == 3.0
    assert hazard.variables[1].rp is None


def test_settings_variables_required(
    hazard_event_path: Path,
    vulnerability_path: Path,
    testdata_dir: Path,
):
    # The variables are required and can not be empty
    for cls, file in (
        (Hazard, hazard_event_path),
        (Vulnerability, vulnerability_path),
        (ExposureGrid, Path(testdata_dir, "exposure", "spatial.nc")),
    ):
        with pytest.raises(ValidationError, match="variables"):
            cls(file=file)
        with pytest.raises(ValidationError, match="variables"):
            cls(file=file, variables=[])


def test_settings_exposure_variable_type_required():
    # The type is required and must be known
    with pytest.raises(ValidationError, match="type"):
        ExposureGridVariable(name="exposure_values", vulnerability="default")
    var = ExposureGridVariable(
        name="exposure_values", type="values", vulnerability="default"
    )
    assert var.type == "values"


def test_settings_exposure_variable_vulnerability():
    # Required for the layers (default) and the category value variables
    with pytest.raises(ValidationError, match="'vulnerability' is required"):
        ExposureGridVariable(name="exposure1", type="default", fn_curve="struct_1")
    with pytest.raises(ValidationError, match="'vulnerability' is required"):
        ExposureGridVariable(name="exposure_values", type="values")

    # Not applicable to the categorized layer itself
    with pytest.raises(ValidationError, match="not allowed"):
        ExposureGridVariable(
            name="exposure", type="categorized", vulnerability="default"
        )
    ExposureGridVariable(name="exposure", type="categorized")


def test_settings_risk_requires_rp(settings_files: Callable[[str], Path]):
    # Load the risk settings and drop a return period from a hazard variable
    settings = load_settings(settings_files("grid_risk.toml"))
    data = settings.to_dict()
    assert data["risk"]
    del data["hazard"]["variables"][0]["rp"]

    # Assert the validation error
    with pytest.raises(ValidationError, match="Return period"):
        GridSettings.model_validate(data, context=settings.context)

    # Not needed for an event
    data["risk"] = False
    GridSettings.model_validate(data, context=settings.context)
