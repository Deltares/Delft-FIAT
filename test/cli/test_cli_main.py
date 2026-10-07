import pytest
from pytest_mock import MockerFixture

import fiat.cli.main as cli_main


def test_main_help(capsys):
    # An empty argv shows the help and exits cleanly
    with pytest.raises(SystemExit) as exc:
        cli_main.main([])

    # Assert the output
    assert exc.value.code == 0
    assert "Usage: fiat <options> <commands>" in capsys.readouterr().out


def test_main_version(capsys, mocker: MockerFixture):
    # The version flag prints the version and exits
    mocker.patch.object(cli_main.sys, "argv", ["fiat", "--version"])

    # Call the function
    with pytest.raises(SystemExit) as exc:
        cli_main.main(["use-sys-argv"])

    # Assert the output
    assert exc.value.code == 0
    assert "FIAT " in capsys.readouterr().out


def test_main_run_grid(run_config, run_patches, mocker: MockerFixture):
    # Run the grid model with cli overrides
    mocker.patch.object(
        cli_main.sys,
        "argv",
        [
            "fiat",
            "run",
            str(run_config.filepath),
            "--threads",
            "3",
            "-d",
            f"{cli_main.MODEL_TYPE}={cli_main.GRID}",
            "-d",
            "custom.values=[1,2]",
        ],  # fmt: skip
    )

    # Call the function
    cli_main.main(["use-sys-argv"])

    # Assert the overrides landed on the config
    assert run_config.values[cli_main.MODEL_THREADS] == 3
    assert run_config.values[cli_main.MODEL_TYPE] == cli_main.GRID
    assert run_config.values["custom.values"] == [1, 2]
    assert run_config.output_dir_was_setup is True

    # Assert the grid model was selected and run
    run_patches.config_entries.assert_called_once_with(
        run_config,
        cli_main.MANDATORY_MODEL_ENTRIES + cli_main.MANDATORY_GRID_ENTRIES,
    )
    run_patches.grid_model.assert_called_once_with(run_config)
    run_patches.grid_model.return_value.run.assert_called_once_with()
    run_patches.geom_model.assert_not_called()


def test_main_run_geom(run_config, run_patches, mocker: MockerFixture):
    # Run without a model type, the geom model is the default
    mocker.patch.object(cli_main.sys, "argv", ["fiat", "run", str(run_config.filepath)])

    # Call the function
    cli_main.main(["use-sys-argv"])

    # Assert the geom model was selected and run
    run_patches.config_entries.assert_called_once_with(
        run_config,
        cli_main.MANDATORY_MODEL_ENTRIES + cli_main.MANDATORY_GEOM_ENTRIES,
    )
    run_patches.geom_model.assert_called_once_with(run_config)
    run_patches.geom_model.return_value.run.assert_called_once_with()
    run_patches.grid_model.assert_not_called()
