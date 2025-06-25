import datetime
import io
import sys
from pathlib import Path

from fiat.log.formatter import MessageFormatter
from fiat.log.handler import FileHandler, StreamHandler, _destruct_handlers, _handlers
from fiat.log.util import LogItem


def test_streamhandler():
    # Setup the object
    h = StreamHandler(level=2)

    # Assert some simple stuff
    assert h.level == 2
    assert isinstance(h.stream, io.TextIOWrapper)


def test_streamhandler_emit(
    log_capture: io.StringIO,
    log_item: LogItem,
):
    # Setup the object
    # Force into a buffer to get the output
    h = StreamHandler(level=2, stream=log_capture)
    assert h._name == "Stream1"

    # Emit a message
    h.emit(log_item)

    # Assert the message in the logging
    log_capture.seek(0)
    cap = log_capture.read()
    assert "A logging message" in cap
    assert "INFO" in cap
    assert datetime.datetime.now().strftime("%Y-%m-%d") in cap


def test_streamhandler_formatter(
    log_capture: io.StringIO,
    log_item: LogItem,
    formatter: MessageFormatter,
):
    # Setup the object
    h = StreamHandler(level=2, stream=log_capture)
    # Set the formatter
    h.set_formatter(formatter)  # This has no datetime in it

    # Emit a message
    h.emit(log_item)

    # Assert the message in the logging
    log_capture.seek(0)
    cap = log_capture.read()
    assert "A logging message" in cap
    assert "INFO" in cap
    # No longer a datetime as a result of the custom formatter
    assert datetime.datetime.now().strftime("%Y-%m-%d") not in cap


def test_streamhandler_close():
    # Setup the object
    h = StreamHandler(level=2, name="stream")

    # Assert it's in the handlers weak dictionary
    assert "stream" in list(_handlers.keys())
    assert not h.closed

    # Close the handler
    h.close()

    # Assert it's gone
    assert "stream" not in list(_handlers.keys())
    assert h.closed

    # De-ref the stream
    # However the stream itself stays open, imagine if you close the stdout :P
    assert h.stream is None
    assert not sys.stdout.closed


def test_filehandler(tmp_path: Path):
    # Setup the object
    f = FileHandler(level=2, dst=tmp_path)

    # Assert some simple stuff
    assert f.level == 2
    assert f._path == Path(tmp_path, "log_default.log")
    assert Path(tmp_path, "log_default.log").is_file()


def test_filehandler_emit(
    tmp_path: Path,
    log_item: LogItem,
):
    # Setup the object
    f = FileHandler(level=2, dst=tmp_path, name="tmp")

    # Assert some simple stuff
    f.emit(log_item)

    # Assert its content
    with open(f._path, "r") as reader:
        data = reader.read()
    assert "A logging message" in data


def test_filehandler_close(
    tmp_path: Path,
):
    # Setup the object
    f = FileHandler(level=2, dst=tmp_path, name="tmp")

    # Assert it's in the handlers weak dictionary
    assert "tmp" in list(_handlers.keys())
    assert not f.closed

    # Set stream to var for assert is closed later
    s = f.stream

    # Close the handler
    f.close()

    # Assert it's gone and more importantly, the stream is closed
    assert "tmp" not in list(_handlers.keys())
    assert f.closed
    assert s.closed


def test_handler_destruct(tmp_path: Path):
    # Setup the object
    h = StreamHandler(level=2, name="stream")
    f = FileHandler(level=2, dst=tmp_path, name="tmp")

    # Assert presence in handler dict
    assert "stream" in list(_handlers.keys())
    assert "tmp" in list(_handlers.keys())

    # Call the atexit registered function
    _destruct_handlers()

    # Assert the handlers are gone
    assert "stream" not in list(_handlers.keys())
    assert "tmp" not in list(_handlers.keys())
    # Assert closed
    assert h.closed
    assert f.closed
