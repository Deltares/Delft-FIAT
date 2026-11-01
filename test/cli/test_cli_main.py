from pathlib import Path
from typing import Callable, Generator
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

import fiat.cli.main as cli_main
from fiat.settings import GeomSettings, GridSettings


def test_main_help(capsys):
    # An empty argv shows the help and exits cleanly
    with pytest.raises(SystemExit) as exc:
        cli_main.main([])

    # Assert the output
    assert exc.value.code == 0
    assert "Usage: fiat <options> <commands>" in capsys.readouterr().out


def test_main_version(
    capsys: Generator[pytest.CaptureFixture[str], None, None],
    mocker: MockerFixture,
):
    # The version flag prints the version and exits
    mocker.patch.object(cli_main.sys, "argv", ["fiat", "--version"])

    # Call the function
    with pytest.raises(SystemExit) as exc:
        cli_main.main(["use-sys-argv"])

    # Assert the output
    assert exc.value.code == 0
    assert "FIAT " in capsys.readouterr().out


def test_main_run_geom(
    run_patches: Mock,
    mocker: MockerFixture,
    settings_files: Path,
    model_settings: GeomSettings,
):
    # Get the settings
    file = settings_files("geom_event.toml")
    settings = model_settings(file)
    # Mock loading the config file
    load_settings = mocker.patch(
        "fiat.cli.main.load_settings",
        return_value=settings,
    )
    run_patches.load_settings = load_settings

    # Run without a model type, the geom model is the default
    mocker.patch.object(
        cli_main.sys,
        "argv",
        ["fiat", "run", str(file)],
    )

    # Call the function
    cli_main.main(["use-sys-argv"])

    # Assert the geom model was selected and run
    run_patches.geom_model.assert_called_once_with(settings)
    run_patches.geom_model.return_value.run.assert_called_once_with()
    run_patches.grid_model.assert_not_called()


def test_main_run_grid(
    run_patches: Mock,
    mocker: MockerFixture,
    settings_files: Callable[[str], Path],
    model_settings: Callable[[str], GridSettings],
):
    # Get the file and settings
    file = settings_files("grid_event.toml")
    settings = model_settings(file)
    # Mock loading the config file
    load_settings = mocker.patch(
        "fiat.cli.main.load_settings",
        return_value=settings,
    )
    run_patches.load_settings = load_settings

    # Run the grid model with cli overrides
    mocker.patch.object(
        cli_main.sys,
        "argv",
        [
            "fiat",
            "run",
            file.as_posix(),
            "-t",
            "1",
            "-s",
            "output_dir=tmp",
        ],
    )

    # Call the function
    cli_main.main(["use-sys-argv"])

    # Assert the overrides landed on the config
    assert settings.threads == 1
    assert settings.output_dir == Path(settings.context.config_dir, "tmp")

    # Assert the grid model was selected and run
    run_patches.grid_model.assert_called_once_with(settings)
    run_patches.grid_model.return_value.run.assert_called_once_with()
    run_patches.geom_model.assert_not_called()


def test_main_run_threads(
    run_patches: Mock,
    mocker: MockerFixture,
    tmp_path: Path,
    settings_files: Callable[[str], Path],
    model_settings: Callable[[str], GridSettings],
):
    # Get the file and settings
    file = settings_files("grid_event.toml")
    settings = model_settings(file)
    # Mock loading the config file
    mocker.patch("fiat.cli.main.load_settings", return_value=settings)

    # Run with only the threads override
    mocker.patch.object(
        cli_main.sys,
        "argv",
        [
            "fiat",
            "run",
            file.as_posix(),
            "--threads",
            "2",
            "-s",
            f"output_dir={tmp_path.as_posix()}",
        ],
    )

    # Call the function
    cli_main.main(["use-sys-argv"])

    # Assert the override landed on the config
    assert settings.threads == 2


@pytest.mark.parametrize(
    ("flags", "level"),
    [
        ([], 2),
        (["-q"], 3),
        (["-qq"], 4),
        (["-qqqq"], 5),  # Clipped to the highest level
        (["-v"], 1),
        (["-vv"], 1),  # Clipped to the lowest level
        (["-q", "-v"], 2),
    ],
)
def test_main_run_loglevel(
    run_patches: Mock,
    mocker: MockerFixture,
    tmp_path: Path,
    settings_files: Callable[[str], Path],
    model_settings: Callable[[str], GridSettings],
    flags: list[str],
    level: int,
):
    # Get the file and settings, the default log level is INFO (2)
    file = settings_files("grid_event.toml")
    settings = model_settings(file)
    assert settings.loglevel == "INFO"
    # Mock loading the config file
    mocker.patch("fiat.cli.main.load_settings", return_value=settings)

    # Run with the quiet/ verbose flags
    mocker.patch.object(
        cli_main.sys,
        "argv",
        [
            "fiat",
            "run",
            file.as_posix(),
            "-s",
            f"output_dir={tmp_path.as_posix()}",
            *flags,
        ],
    )

    # Call the function
    cli_main.main(["use-sys-argv"])

    # Assert the log level, higher is less output
    assert run_patches.logger.level == level
