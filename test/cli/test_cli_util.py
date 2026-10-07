from pathlib import Path
from typing import Generator

import pytest
from pytest_mock import MockerFixture

from fiat.cli.util import file_path_check, run_log, run_profiler


def test_file_path_check(
    monkeypatch: Generator[pytest.MonkeyPatch, None, None],
    tmp_path: Path,
):
    # Set a file and a directory to find
    config = tmp_path / "settings.toml"
    config.write_text("[model]\n", encoding="utf-8")
    output = tmp_path / "output"
    output.mkdir()
    monkeypatch.chdir(tmp_path)

    # A relative file and a directory both resolve
    assert file_path_check("settings.toml") == config
    assert file_path_check(output) == output


def test_file_path_check_error(
    monkeypatch: Generator[pytest.MonkeyPatch, None, None],
    tmp_path: Path,
):
    monkeypatch.chdir(tmp_path)

    # A non existing path raises
    with pytest.raises(
        FileNotFoundError,
        match="missing.toml is not a valid path",
    ):
        file_path_check("missing.toml")


def test_run_log(mocker: MockerFixture):
    # A succeeding function returns its output
    func = mocker.Mock(return_value="done")
    logger = mocker.Mock()

    # Call the function
    out = run_log(func, logger, "arg")

    # Assert the output
    assert out == "done"
    func.assert_called_once_with("arg")
    logger.error.assert_not_called()


def test_run_log_error(mocker: MockerFixture):
    # A raising function is logged and exits with code 1
    def raises():
        raise ValueError("bad", "value")

    logger = mocker.Mock()

    # Call the function
    with pytest.raises(SystemExit) as exc:
        run_log(raises, logger)

    # Assert the output
    assert exc.value.code == 1
    logger.error.assert_called_once_with("bad,value")


def test_run_log_interrupt(mocker: MockerFixture):
    # A keyboard interrupt is logged by name
    def raises():
        raise KeyboardInterrupt

    logger = mocker.Mock()

    # Call the function
    with pytest.raises(SystemExit) as exc:
        run_log(raises, logger)

    # Assert the output
    assert exc.value.code == 1
    logger.error.assert_called_once_with("KeyboardInterrupt")


def test_run_profiler(
    tmp_path: Path,
    mocker: MockerFixture,
    profiler_config,
):
    # Set a function to profile
    func = mocker.Mock(return_value=None)
    logger = mocker.Mock()

    # Call the function
    run_profiler(func, profile="profile", cfg=profiler_config, logger=logger)

    # Assert both profile outputs were written
    func.assert_called_once_with()
    assert (tmp_path / "profile").is_file()
    txt = tmp_path / "profile.txt"
    assert txt.is_file()
    assert f"Delft-FIAT profile ({profiler_config.filepath})" in txt.read_text(
        encoding="utf-8"
    )
    logger.warning.assert_called_once_with("Running profiler...")
