import atexit
import io
import os
import sys
import threading
import weakref
from datetime import datetime
from enum import Enum

STREAM_COUNT = 1

_Global_and_Destruct_Lock = threading.RLock()
_streams = weakref.WeakValueDictionary()
_loggers = weakref.WeakValueDictionary()


class LogItem:
    def __init__(
        self,
        level: str,
        msg: str,
    ):
        """_summary_"""

        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.level = level
        self.msg = msg

    def __str__(self):
        return f"{self.timestamp:20s} {self.level:8s} {self.msg}\n"


def _Destruction():
    """_summary_"""

    items = list(_streams.items())
    for _, logger in items:
        logger.acquire()
        logger.flush()
        logger.close()
        logger.release()


atexit.register(_Destruction)


def _Level(level):
    """_summary_"""

    if level not in LogLevels._value2member_map_:
        raise ValueError("")
    return level


class LogLevels(Enum):
    """_summary_"""

    DEBUG = 1
    INFO = 2
    WARNING = 3
    ERROR = 4
    DEAD = 5


class StreamLogger:
    def __init__(
        self,
        level: int = 2,
        name: str = None,
        stream: type = None,
    ):
        """_summary_

        Parameters
        ----------
        level : int, optional
            _description_, by default 2
        name : str, optional
            _description_, by default None
        stream : type, optional
            _description_, by default None
        """

        self._closed = False
        self.level = _Level(level)

        if stream is None:
            stream = sys.stdout
        self.stream = stream

        if name is None:
            if hasattr(self.stream, "name"):
                self._name = self.stream.name
            else:
                global STREAM_COUNT
                self._name = f"Generic_Stream{STREAM_COUNT}"
                STREAM_COUNT += 1
        else:
            self._name = name

        _streams[self._name] = self

        self._lock = threading.RLock()

    def acquire(self):
        self._lock.acquire()

    def release(self):
        self._lock.release()

    def emit(self, msg):
        self.stream.write(msg)
        self.flush()

    def flush(self):
        self.acquire()
        self.stream.flush()
        self.release()

    def close(self):
        _Global_and_Destruct_Lock.acquire()
        self._closed = True
        del _streams[self._name]
        _Global_and_Destruct_Lock.release()


class FileLogger(StreamLogger):
    def __init__(self, level: int, dst: str, name: str = None):
        """_summary_

        Parameters
        ----------
        level : int
            _description_
        dst : str
            _description_
        name : str, optional
            _description_, by default None
        """

        if name is None:
            name = "fiat_logging"
        self._filename = os.path.join(dst, f"{name}.log")
        StreamLogger.__init__(self, level, name, self._open())

    def _open(self):
        """_summary_"""

        return open(self._filename, "w")

    def close(self):
        """_summary_"""

        self.acquire()
        self.flush()

        stream = self.stream
        self.stream = None

        stream.close()
        StreamLogger.close(self)
        self.release()


def spawn_child_logger(
    name: str,
) -> "Log":
    """_summary_

    Parameters
    ----------
    name : str
        _description_

    Returns
    -------
    Log
        _description_
    """

    idx = name.rfind(".")
    if not name[:idx] in _loggers:
        raise ValueError(f"Unknown parent logger: {name[:idx]}")

    parent = _loggers[name[:idx]]

    log = Log(name, parent.log_level)
    log.parent = parent
    log.main = False

    return log


class Log:
    def __init__(
        self,
        name: str,
        log_level: int = 2,
    ):
        """_summary_

        Parameters
        ----------
        name : str
            _description_
        log_level : int, optional
            _description_, by default 2
        """

        self.log_level = log_level
        self.main = True
        self.name = name
        self.parent = None
        self._streams = []

        _loggers[self.name] = self

    def __del__(self):
        pass

    def _log(self, item):
        """_summary_"""

        obj = self
        while obj:
            for logger in obj._streams:
                if LogLevels[item.level].value < logger.level:
                    continue
                else:
                    logger.emit(str(item))
            if obj.main:
                obj = None
            else:
                obj = obj.parent

    def handleLog(log_m):
        def handle(self, *args, **kwargs):
            lvl, msg = log_m(self, *args, **kwargs)
            self._log(LogItem(level=lvl, msg=msg))

        return handle

    def add_loggers(
        self,
        dst: str,
        name: str = None,
        cmd_stream: bool = True,
        cmd_level_diff: int = 0,
    ):
        """_summary_

        Parameters
        ----------
        dst : str
            _description_
        cmd_stream : bool, optional
            _description_, by default True
        cmd_level_diff : int, optional
            _description_, by default 0
        """

        self._streams.append(FileLogger(level=self.log_level, dst=dst, name=self.name))
        if cmd_stream:
            self._streams.append(StreamLogger(level=(self.log_level - cmd_level_diff)))

    @handleLog
    def debug(self, msg: str):
        """_summary_"""

        return "DEBUG", msg

    @handleLog
    def info(self, msg: str):
        """_summary_"""

        return "INFO", msg

    @handleLog
    def warning(self, msg: str):
        """_summary_"""

        return "WARNING", msg

    @handleLog
    def error(self, msg: str):
        """_summary_"""

        return "ERROR", msg

    @handleLog
    def dead(self, msg: str):
        """_summary_"""

        return "DEAD", msg

    def direct(self, msg):
        """_summary_"""

        self._log()
