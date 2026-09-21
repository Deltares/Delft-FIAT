"""Buffered writers."""

import os
from io import BytesIO, FileIO
from multiprocessing.synchronize import Lock
from pathlib import Path

from fiat.util import (
    NEWLINE_CHAR,
    DummyLock,
)

__all__ = ["BufferedTextWriter"]


class BufferedTextWriter(BytesIO):
    """Write text in chunks.

    Parameters
    ----------
    file : Path | str
        Path to the file.
    mode : str, optional
        Mode for opening the file. Byte-mode is mandatory, by default "wb"
    buffer_size : int, optional
        The size of the buffer, by default 524288 (which is 512 kb)
    """

    def __init__(
        self,
        file: Path | str,
        mode: str = "wb",
        buffer_size: int = 524288,  # 512 kB
        lock: Lock = None,
    ):
        # Set the lock
        self.lock = lock
        if lock is None:
            self.lock = DummyLock()

        BytesIO.__init__(self)

        # Set object specific stuff
        self.stream = FileIO(
            file=file,
            mode=mode,
        )
        self.max_size = buffer_size

    def close(self) -> None:
        """Close the writer and the buffer."""
        # Flush on last time
        self.dump()
        self.stream.close()

        # Close the buffer
        BytesIO.close(self)

    ## I/O
    def dump(self) -> None:
        """Dump to buffer to the drive."""
        self.seek(0)

        # Push data to the file
        self.lock.acquire()
        self.stream.write(self.read())
        self.stream.flush()
        os.fsync(self.stream)
        self.lock.release()

        # Reset the buffer
        self.truncate(0)
        self.seek(0)

    ## Mutating methods
    def add(
        self,
        b: bytes,
    ) -> None:
        """Write bytes to the buffer.

        Parameters
        ----------
        b : bytes
            Bytes to write.
        """
        if self.tell() + len(b) > self.max_size:
            self.dump()
        self.write(b)

    def add_iterable(self, *args) -> None:
        """Write a multiple entries to the buffer."""
        by = b""
        for arg in args:
            by += ("," + "{}," * len(arg)).format(*arg).rstrip(",").encode()
        by = by.lstrip(b",")
        by += NEWLINE_CHAR.encode()
        self.add(by)
