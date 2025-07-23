import io
import sys
from pathlib import Path

from fiat.log.logger import BaseLogger, Logger, LogManager


def test_logger():
    # Create the object
    l = Logger("tmp", level=2)

    # Assert some simple stuff
    assert l.name == "tmp"
    assert l.level == 2
    assert l.parent is None
    assert isinstance(l.manager, LogManager)


def test_logger_handlers(tmp_path: Path):
    # Create the object
    l = Logger("tmp", level=2)

    # Add the handlers
    l.add_stream_handler(level=2, name="stream", stream=sys.stdout)
    l.add_file_handler(level=2, dst=tmp_path)

    # Assert the presence of the handlers
    assert len(l._handlers) == 2
    assert l._handlers[0]._name == "stream"
    assert l._handlers[1]._name == "log_default"


def test_logger_emit(
    log_capture: io.StringIO,
):
    # Create the object
    l = Logger("tmp", level=1)  # Debug mode for testing
    # Add a handler
    l.add_stream_handler(level=1, name="stream", stream=log_capture)

    # Emit messages
    l.debug("Debug message")
    l.info("Info message")
    l.warning("Warning message")
    l.error("Error message")
    l.dead("Dead message")

    # Assert the outputs
    log_capture.seek(0)
    cap = log_capture.read()
    assert "Debug message" in cap
    assert "Info message" in cap
    assert "Warning message" in cap
    assert "Error message" in cap
    assert "Dead message" in cap


def test_logger_level():
    # Create the object
    l = Logger("tmp_level", level=1)  # Debug mode for testing
    # Add a handler
    l.add_stream_handler(level=1, name="stream", stream=sys.stdout)

    # Assert level
    assert l.level == 1
    assert l._handlers[0].level == 1

    # Set a new level
    l.level = 2

    # Assert level
    assert l.level == 2
    assert l._handlers[0].level == 2


def test_logger_child():
    # Create the object
    l = Logger("tmp", level=2)

    # Create a child logger
    lc = Logger("tmp.child", level=2)
    # Assert it's name
    assert lc.name == "tmp.child"

    # Assert it's parent
    id(lc.parent) == id(l)


def test_logger_grandchild():
    # Create the object
    l = Logger("x", level=2)

    # Create a child logger
    lgc = Logger("x.y.z", level=2)
    # Assert it's name
    assert lgc.name == "x.y.z"
    assert isinstance(l.manager.logger_tree["x.y"], BaseLogger)

    # Assert it's parent
    id(lgc.parent) == id(l)


def test_logger_parent():
    # Create the object
    l = Logger("tmp.child", level=2)

    # Assert the state of tree as when the parent is unknown a dummylog stub is created
    assert isinstance(l.manager.logger_tree["tmp"], BaseLogger)

    # Create the parent logger
    lp = Logger("tmp", level=2)

    # Assert that 'tmp' is not a logger object in the tree
    assert isinstance(lp.manager.logger_tree["tmp"], Logger)
    assert id(l.parent) == id(lp)


def test_logger_grandparent():
    # Create the object
    l = Logger("c.b.a", level=2)

    # Assert the state of tree as when the parent is unknown
    assert isinstance(l.manager.logger_tree["c"], BaseLogger)
    assert isinstance(l.manager.logger_tree["c.b"], BaseLogger)

    # Create the parent logger
    lp = Logger("c", level=2)

    # Assert that 'tmp' is not a logger object in the tree
    assert isinstance(lp.manager.logger_tree["c"], Logger)
    assert isinstance(l.manager.logger_tree["c.b"], BaseLogger)
    assert id(l.parent) == id(lp)


def test_logger_known():
    # Create the object
    l = Logger("tmp", level=2)

    # Create a new logger with the same name
    l2 = Logger("tmp", level=2)

    # That's a no-no, the old logger will be returned
    assert id(l) == id(l2)
