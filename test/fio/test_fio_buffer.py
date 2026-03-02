from multiprocessing import get_context
from multiprocessing.synchronize import Lock
from pathlib import Path

from fiat.fio.buffer import BufferedTextWriter
from fiat.util import NEWLINE_CHAR, DummyLock


def test_buffered_text_writer_init(tmp_path: Path):
    p = Path(tmp_path, "tmp.txt")
    # Create the writer
    w = BufferedTextWriter(p, buffer_size=20)  # 20 chars

    # Assert some simple stuff
    assert isinstance(w.lock, DummyLock)
    assert w.max_size == 20


def test_buffered_text_writer_init_lock(tmp_path: Path):
    p = Path(tmp_path, "tmp.txt")
    # Create the writer
    w = BufferedTextWriter(
        p,
        lock=Lock(ctx=get_context()),
    )

    # Assert some simple stuff
    assert isinstance(w.lock, Lock)


def test_buffered_text_writer_write(tmp_path: Path):
    p = Path(tmp_path, "tmp.txt")
    # Create the writer
    w = BufferedTextWriter(p)

    # Add data like a dummy
    w.add(b"")

    # Write the buffer, (also called in `close`)
    w.dump()

    # Assert that it is empty
    assert w.tell() == 0
    assert w.getbuffer().nbytes == 0

    # Close it
    w.close()


def test_buffered_text_writer_add(tmp_path: Path):
    p = Path(tmp_path, "tmp.txt")
    # Create the writer
    w = BufferedTextWriter(p, buffer_size=20)  # 20 chars

    # Write something to the buffer
    w.add(b"foo,bar,baz,var\n")  # 16 chars

    # Assert its in the buffer
    assert w.tell() == 16
    assert w.getbuffer().nbytes == 16  # Or more technical

    # Verify the content
    w.seek(0)  # Go the the start of the buffer
    content = w.read()
    assert content == b"foo,bar,baz,var\n"


def test_buffered_text_writer_add_write(tmp_path: Path):
    p = Path(tmp_path, "tmp.txt")
    # Create the writer
    w = BufferedTextWriter(p, buffer_size=20)  # 20 chars

    # Write more to the buffer
    w.add(b"foo,bar,baz,var\n")  # 16 chars
    w.add(b"foo,bar,baz\n")  # 12 chars

    # This should have triggerd a dump as 16 + 12 > 20
    assert w.tell() == 12


def test_buffered_text_writer_add_iterable(tmp_path: Path):
    p = Path(tmp_path, "tmp.txt")
    # Create the writer
    w = BufferedTextWriter(p, buffer_size=20)  # 20 chars

    # Write something to the buffer
    w.add_iterable(["foo", "bar", "baz", "var"])  # 16 chars (newline included)

    # Assert its in the buffer
    assert w.tell() == 15 + len(NEWLINE_CHAR)
    assert w.getbuffer().nbytes == 15 + len(NEWLINE_CHAR)  # Or more technical

    # Verify the content
    w.seek(0)  # Go the the start of the buffer
    content = w.read()
    assert content == f"foo,bar,baz,var{NEWLINE_CHAR}".encode()
