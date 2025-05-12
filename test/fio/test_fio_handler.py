import pickle
from io import BufferedReader
from pathlib import Path

from fiat.fio.handler import BufferHandler


def test_buffer_handler_basic(exposure_data_path: Path):
    # Open the handler
    h = BufferHandler(exposure_data_path)

    # Assert some simple stuff
    assert h.nchar == b"\n"
    assert h.size == 6  # Number of lines
    assert h.skip == 0  # No skip yet defined
    assert isinstance(h.stream, BufferedReader)  # The stream
    assert h.stream.closed == False  # Open stream

    # Read a little
    line = h.stream.readline()
    assert line.startswith(b"object_id,extract_method")  # Part of the header

    # Close the handler
    h.close()
    assert h.stream is None


def test_buffer_handler_context(exposure_data_path: Path):
    # Open the handler
    h = BufferHandler(exposure_data_path)

    # Open the handler via context manager
    with h as handler:
        # Assert some stuff in the manager, it returns the internal stream
        line = handler.readline()
        assert line.startswith(b"object_id,extract_method")  # Part of the header

    # After it should not be deleted or closed
    assert h.stream.closed == False
    assert h.stream.tell() == h.skip


def test_buffer_handler_reduce(exposure_data_path: Path):
    # Open the handler
    h = BufferHandler(exposure_data_path)

    # Dump it to bytes
    dump = pickle.dumps(h)

    # Assert the result
    assert isinstance(dump, bytes)

    # Rebuild the handler
    obj = pickle.loads(dump)

    # Assert the object
    assert isinstance(obj, BufferHandler)
