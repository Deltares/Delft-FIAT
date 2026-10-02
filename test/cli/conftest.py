from pathlib import Path

import pytest
from pytest_mock import MockerFixture

import fiat.cli.main as cli_main
from fiat.util import OUTPUT_PATH


## Configuration test doubles used as cli input
class ProfilerConfig:
    """Minimal config exposing what run_profiler needs."""

    def __init__(self, output_path: Path):
        self.filepath = output_path / "settings.toml"
        self._output_path = output_path

    def get(self, key, default=None):
        if key == OUTPUT_PATH:
            return self._output_path
        return default


class RunConfig:
    """Minimal config double driving the cli run command."""

    def __init__(self, output_path: Path):
        self.filepath = output_path / "settings.toml"
        self.values = {
            cli_main.MODEL_LOGLEVEL: "INFO",
            cli_main.OUTPUT_PATH: output_path,
        }
        self.output_dir_was_setup = False

    def set(self, key, value):
        self.values[key] = value

    def update(self, entries):
        self.values.update(entries)

    def setup_output_dir(self):
        self.output_dir_was_setup = True

    def get(self, key, default=None):
        return self.values.get(key, default)


@pytest.fixture
def profiler_config(tmp_path: Path) -> ProfilerConfig:
    return ProfilerConfig(tmp_path)


@pytest.fixture
def run_config(tmp_path: Path) -> RunConfig:
    cfg = RunConfig(tmp_path)
    cfg.filepath.write_text("[model]\n", encoding="utf-8")
    return cfg


@pytest.fixture
def run_patches(mocker: MockerFixture, run_config: RunConfig):
    """Patch the run command dependencies and expose the mocks."""
    logger = mocker.Mock()
    setup_log = mocker.patch("fiat.cli.main.setup_default_log", return_value=logger)
    from_file = mocker.patch(
        "fiat.cli.main.Configurations.from_file", return_value=run_config
    )
    loglevel = mocker.patch("fiat.cli.main.check_loglevel", return_value=2)
    config_entries = mocker.patch("fiat.cli.main.check_config_entries")
    geom_model = mocker.Mock(name="GeomModel")
    grid_model = mocker.Mock(name="GridModel")
    mocker.patch.dict(
        cli_main._models,
        {
            cli_main.GEOM: {
                cli_main.MODEL: geom_model,
                cli_main.INPUT: cli_main.MANDATORY_GEOM_ENTRIES,
            },
            cli_main.GRID: {
                cli_main.MODEL: grid_model,
                cli_main.INPUT: cli_main.MANDATORY_GRID_ENTRIES,
            },
        },
    )
    return mocker.Mock(
        logger=logger,
        setup_log=setup_log,
        from_file=from_file,
        loglevel=loglevel,
        config_entries=config_entries,
        geom_model=geom_model,
        grid_model=grid_model,
    )
