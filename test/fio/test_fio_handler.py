import pickle
from io import BufferedReader, BytesIO
from pathlib import Path

import pytest

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


def test_buffer_handler_newline(exposure_data_win_path: Path):
    # Open the handler
    h = BufferHandler(exposure_data_win_path)

    # Assert that the newline is windows like (not unix)
    assert h.nchar == b"\r\n"
    assert h.size == 6

    # Read a little, should be the same
    line = h.stream.readline()
    assert line.startswith(b"object_id,extract_method")  # Part of the header


def test_buffer_handler_newline_back(exposure_data_path: Path):
    # Open the handler
    h = BufferHandler(exposure_data_path)

    # Bit of voodoo to remove the last newline char
    buffer = BytesIO()
    buffer.write(h.stream.read())
    buffer.seek(buffer.tell() - 1)  # Move back in front of the last newline char
    buffer.truncate()  # Remove the newline char
    buffer.seek(0)  # Move back to the front
    # Set the buffer as the stream
    h.stream = buffer

    # The size of the stream with the last newline char included was 6
    # Should also be 6 now
    h.stream_info()
    assert h.size == 6


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


def test_buffer_handler_errors(exposure_data_path: Path):
    # Open the handler
    h = BufferHandler(exposure_data_path)

    # This part is a bit hacky, but direct setting of a stream is not supported
    buffer = BytesIO()
    # Write lines with a mix of Windows and Unix newline chars
    char = "\n"
    for idx in range(9):
        if idx % 2 != 0:
            char = "\r\n"
        buffer.write(f"1,2,3,4{char}".encode())
        char = "\n"

    # Set the buffer directly
    h.stream = buffer

    # Verify that the sniffer doesnt like this
    with pytest.raises(
        ValueError,
        match="Mixed newline characters",
    ):
        h.sniffer()
