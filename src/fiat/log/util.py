"""Logging utility."""

import threading
import time
from enum import Enum

__all__ = ["LogItem"]

DEFAULT_FMT = "{asctime:20s}{levelname:8s}{message}"
DEFAULT_TIME_FMT = "%Y-%m-%d %H:%M:%S"

_Global_and_Destruct_Lock = threading.RLock()


class LogLevels(Enum):
    """Valid logging levels."""

    DEBUG = 1
    INFO = 2
    WARNING = 3
    ERROR = 4
    DEAD = 5


def global_acquire():
    """Global method for acquiring global lock."""
    if _Global_and_Destruct_Lock:
        _Global_and_Destruct_Lock.acquire()


def global_release():
    """Global method for releasing global lock."""
    if _Global_and_Destruct_Lock:
        _Global_and_Destruct_Lock.release()


def check_loglevel(level):
    """Check if level can be used."""
    if isinstance(level, int) and level not in LogLevels._value2member_map_:
        raise ValueError(f"Level ({level}) is not a valid log level.")
    elif isinstance(level, str):
        level = level.upper()
        if level not in LogLevels._member_map_:
            raise ValueError(f"Level ({level}) is not a valid log level.")
        else:
            level = LogLevels[level].value
    elif not isinstance(level, (int, str)):
        raise TypeError(
            f"Level ({level}) of incorrect type -> type: {type(level).__name__}",
        )
    return level


class LogItem:
    """A logging item.

    Parameters
    ----------
    level : str
        Logging level.
    msg : str
        The message.
    """

    def __init__(
        self,
        level: str,
        msg: str,
    ):
        self.ct = time.time()
        self.level = level
        self.levelname = LogLevels(level).name
        self.msg = msg

    def get_message(
        self,
    ):
        """Return the message."""
        return str(self.msg)
