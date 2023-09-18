from delft_fiat.log import CHandler, Log, MessageFormatter, spawn_logger

import io
import pytest
from pathlib import Path


def test_stream(log1, log2):
    stream = io.StringIO()
    sl = CHandler(stream=stream)
    sl.set_formatter(MessageFormatter("{message}"))

    sl.emit(log1)
    sl.emit(log2)

    stream.seek(0)
    assert stream.readline().strip() == "Hello!"


def test_log(tmpdir):
    log = Log("test_log", log_level=2)
    log.add_c_handler(
        level=2,
    )
    log.add_file_handler(
        str(tmpdir),
        filename="test_log",
    )
    child_log = spawn_logger("test_log.child")

    assert id(log) != id(child_log)

    log.debug("This message should not be output")
    log.info("Start of test logging")
    log.warning("Warning about stuff")
    log.error("Something has really gone wrong...")
    child_log.error("I also quit!")
    log.dead("Bye")

    del child_log
    del log

    fh = open(Path(str(tmpdir), "test_log.log"), mode="r")

    assert sum(1 for _ in fh) == 5
