from pathlib import Path

from fiat.fio.handler import BufferHandler


def test_buffer_handler_basic(exposure_data_path: Path):
    # Open the handler
    h = BufferHandler(exposure_data_path)

    # Assert some simple stuff
    assert h.nchar == b"\n"
    assert h.size == 6  # Number of lines
    assert h.skip == 0  # No skip yet defined


def test_buffer_handler_context(exposure_data_path: Path):
    # Open the handler via context manager
    with BufferHandler(exposure_data_path) as handler:
        # Assert some stuff in the manager
        assert handler.size == 6
