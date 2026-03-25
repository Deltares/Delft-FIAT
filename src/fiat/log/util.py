"""Logging utility."""

import time
from dataclasses import dataclass
from enum import Enum

__all__ = ["LogItem"]

DEFAULT_FMT = "{asctime:20s}{levelname:8s}{message}"
DEFAULT_TIME_FMT = "%Y-%m-%d %H:%M:%S"


class LogLevels(Enum):
    """Valid logging levels."""

    DEBUG = 1
    INFO = 2
    WARNING = 3
    ERROR = 4
    DEAD = 5


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
    level : int
        Logging level.
    msg : str
        The message.
    """

    def __init__(
        self,
        level: int,
        msg: str,
    ):
        self.ct = time.time()
        self.level: int = level
        self.msg: str = msg

    def get_message(
        self,
    ) -> str:
        """Return the message."""
        return str(self.msg)

    def get_levelname(
        self,
    ) -> str:
        """Return the name of the log level."""
        return LogLevels(self.level).name


@dataclass
class FormatItem:
    """Simple container for the formatter."""

    levelname: str
    message: str
    asctime: str | None = None
