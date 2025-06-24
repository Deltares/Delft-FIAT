"""Base object of I/O."""

import gc
from abc import ABCMeta, abstractmethod
from pathlib import Path

from fiat.util import NEED_IMPLEMENTED


class BaseIO(metaclass=ABCMeta):
    """Base class for objects concerning I/O.

    Parameters
    ----------
    file : Path | str
        Path to the file
    mode : str, optional
        Mode in which to open the file, by default "r"
    """

    _mode_map = {
        "r": 0,
        "a": 1,
        "w": 2,
    }

    def __init__(
        self,
        file: Path | str,
        mode: str = "r",
    ):
        # Current state
        self._closed = False

        # Set the pathing
        self.path: Path = Path(file)
        self._path: Path = Path(file)  # Seems funny, needed later

        # Check the mode
        if mode not in BaseIO._mode_map:
            raise ValueError("Invalid mode, chose from 'r', 'a' or 'w'")

        # Set the mode
        self.mode: int = BaseIO._mode_map[mode]
        self.mode_str: str = mode

        # If read and file doesnt exist, throw error
        if self.mode != 2 and not self.path.is_file():
            raise FileNotFoundError(
                f"{self.path.as_posix()} doesn't exist, can't read",
            )

    def __repr__(self):
        _mem_loc = f"{id(self):#018x}".upper()
        return f"<{self.__class__.__name__} object at {_mem_loc}>"

    def __del__(self):
        if not self._closed:
            self.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def check_mode(m):  # noqa : D102
        def _inner(self, *args, **kwargs):
            if not self.mode:
                raise ValueError("Invalid operation on a read-only file")
            _result = m(self, *args, **kwargs)

            return _result

        return _inner

    def check_state(m):  # noqa : D102
        def _inner(self, *args, **kwargs):
            if self.closed:
                raise ValueError("Invalid operation on a closed file")
            _result = m(self, *args, **kwargs)

            return _result

        return _inner

    def close(self):
        """Close the dataset/ stream."""
        self.flush()
        self._closed = True
        gc.collect()

    @property
    def closed(self) -> bool:
        """Return the state."""
        return self._closed

    @abstractmethod
    def flush(self):
        """Flush the buffer."""
        raise NotImplementedError(NEED_IMPLEMENTED)
