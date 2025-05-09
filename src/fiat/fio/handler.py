"""Stream handlers."""

from io import BufferedReader, FileIO
from pathlib import Path

__all__ = ["BufferHandler"]


class BufferHandler:
    """Handle a buffer connected to a file.

    Parameters
    ----------
    path : Path
        Path to the file.
    skip : int, optional
        Amount of characters to skip at the beginning of the file, by default 0
    """

    def __init__(
        self,
        path: Path,
        skip: int = 0,
    ):
        self.path = Path(path)
        self.size = None
        self.skip = skip
        self.nchar = b"\n"
        self.stream = None

        if self.stream is None:
            self.setup_stream()

    def __repr__(self):
        return f"<{self.__class__.__name__} file='{self.path}' encoding=''>"

    def __getstate__(self):
        if self.stream is not None:
            self.close_stream()
        return self.__dict__

    def __setstate__(self, d):
        self.__dict__ = d
        self.setup_stream()

    def __enter__(self):
        return self.stream.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stream.flush()
        self.stream.seek(self.skip)
        return False

    def close(self):
        """Close the handler."""
        if self.stream is not None:
            self.stream.flush()
            self.close_stream()

    def close_stream(self):
        """Close the steam to the file."""
        self.stream.close()
        self.stream = None
        self.size = None

    def setup_stream(self):
        """Set up the steam to the file."""
        self.stream = BufferedReader(FileIO(self.path))
        self.sniffer()
        self.size = self.stream.read().count(self.nchar)
        self.stream.seek(self.skip)

    def sniffer(self):
        """Sniff for the newline character."""
        raw = self.stream.read(20000)
        r_count = raw.count(b"\r")
        n_count = raw.count(b"\n")
        if n_count > 9 * r_count:
            pass
        elif n_count < 1.1 * r_count:
            self.nchar = b"\r\n"
        else:
            raise ValueError(f"Mixed newline characters in {self.path.as_posix()}")
        self.stream.seek(0)
