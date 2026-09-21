from multiprocessing.queues import Queue
from pathlib import Path

import pytest

from fiat.log.handler import FileHandler, StreamHandler
from fiat.log.logger import Logger
from fiat.log.spawn import setup_default_log, setup_mp_log, spawn_logger
from fiat.log.thread import Receiver


def test_setup_default_log():
    # Call the function
    l = setup_default_log(name="spawn", level=2)

    # assert the output and state
    assert isinstance(l, Logger)
    assert l.level == 2
    assert len(l._handlers) == 1
    assert isinstance(l._handlers[0], StreamHandler)


def test_setup_default_log_file(tmp_path: Path):
    # Call the function
    l = setup_default_log(name="spawn_file", level=2, dst=tmp_path)

    # assert the output and state
    assert l.level == 2
    assert len(l._handlers) == 2
    assert isinstance(l._handlers[1], FileHandler)
    assert Path(tmp_path, "spawn_file.log").is_file()


def test_setup_default_log_errors():
    # Only base names (no periods) are accepted when settings up default
    with pytest.raises(
        ValueError, match=r"Only root names \(without a period\) are allowed."
    ):
        _ = setup_default_log(name="spawn.foo", level=2)


def test_setup_mp_log(
    tmp_path: Path,
    mp_queue: Queue,
):
    # Call the function
    r = setup_mp_log(mp_queue, name="spawn", level=2, dst=tmp_path)

    # assert the output and state
    assert isinstance(r, Receiver)
    assert len(r._handlers) == 1
    assert isinstance(r._handlers[0], FileHandler)
    assert r._handlers[0].level == 2
    assert Path(tmp_path, "spawn.log").is_file()


def test_spawn_logger():
    # Call the function
    l = spawn_logger("spawn")

    # Assert the output
    assert isinstance(l, Logger)
    assert l.name == "spawn"
    assert l.level == 2
