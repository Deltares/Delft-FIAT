import atexit
import io
import os
import sys
import threading
import weakref
from datetime import datetime
from enum import Enum
from warnings import warn

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
        """Struct for logging messages..."""

        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.level = level
        self.msg = msg

    def __str__(self):
        return f"{self.timestamp:20s} {self.level:8s} {self.msg}\n"


def _Destruction():
    """Method called when python exits to clean up"""

    items = list(_streams.items())
    for _, stream in items:
        stream.acquire()
        stream.flush()
        stream.close()
        stream.release()


atexit.register(_Destruction)


def _Level(level):
    """Check if level can be used"""

    if level not in LogLevels._value2member_map_:
        raise ValueError("")
    return level


class LogLevels(Enum):
    """Dumb c-like thing"""

    DEBUG = 1
    INFO = 2
    WARNING = 3
    ERROR = 4
    DEAD = 5


class BaseStream:
    def __init__(
        self,
        level: int = 2,
    ):
        """Base class for all stream handlers"""

        self.level = _Level(level)
        self._name = None
        self._closed = False

        self._make_lock()

    def __repr__(self):
        pass

    def _add_global_stream_ref(
        self,
    ):
        """_summary_"""

        _Global_and_Destruct_Lock.acquire()
        _streams[self._name] = self
        _Global_and_Destruct_Lock.acquire()

    def _make_lock(self):
        self._lock = threading.RLock()

    def acquire(self):
        self._lock.acquire()

    def release(self):
        self._lock.release()

    def close(self):
        """Close and clean up"""

        _Global_and_Destruct_Lock.acquire()
        self._closed = True
        del _streams[self._name]
        _Global_and_Destruct_Lock.release()

    def emit(self):
        NotImplementedError()

    def flush(self):
        NotImplementedError()


class CMDStream(BaseStream):
    def __init__(
        self,
        level: int = 2,
        stream: type = None,
        name: str = None,
    ):
        """Output text to the console

        Parameters
        ----------
        level : int, optional
            _description_, by default 2
        name : str, optional
            _description_, by default None
        stream : type, optional
            _description_, by default None
        """

        BaseStream.__init__(self, level=level)

        if stream is None:
            stream = sys.stdout
        self.stream = stream

        if name is None:
            if hasattr(self.stream, "name"):
                self._name = self.stream.name
            else:
                global STREAM_COUNT
                self._name = f"Stream{STREAM_COUNT}"
                STREAM_COUNT += 1
        else:
            self._name = name

        self._add_global_stream_ref()

    def emit(self, msg):
        """Emit a certain message"""

        self.stream.write(msg)
        self.flush()

    def flush(self):
        """Dump cache to desired destination"""

        self.acquire()
        self.stream.flush()
        self.release()


class FileStream(CMDStream):
    def __init__(
        self,
        level: int,
        dst: str,
        name: str = None,
        mode: str = "w",
    ):
        """Output text to a file

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
            name = "log_default"
        self._filename = os.path.join(dst, f"{name}.log")
        CMDStream.__init__(self, level, self._open(mode), name)

    def _open(
        self,
        mode: str = "w",
    ):
        """Open a txt file and return the handler"""

        return open(self._filename, mode)

    def close(self):
        """Close and clean up"""

        self.acquire()
        self.flush()

        stream = self.stream
        self.stream = None

        stream.close()
        CMDStream.close(self)
        self.release()


class DummyLog:
    def __init__(
        self,
        obj,
    ):
        """Dummy class for tracking children
        (actually funny..)
        """

        self.child_tree = {obj: None}

    def __repr__(self):
        _mem_loc = f"{id(self):#018x}".upper()
        return f"<{self.__class__.__name__} object at {_mem_loc}>"

    def _check_succession(
        self,
        obj,
    ):
        """Remove child if older one is present"""

        _disinherit = [
            child for child in self.child_tree if child.name.startswith(obj.name)
        ]

        for child in _disinherit:
            del self.child_tree[child]

    def add_to_chain(self, obj):
        """_summary_"""

        self._check_succession(obj)
        self.child_tree[obj] = None


class LogManager:
    def __init__(
        self,
        stuff=None,
    ):
        """_summary_"""

        self.logger_tree = {}

    def _check_children(
        self,
        obj: DummyLog,
        logger: "Log",
    ):
        """Ensure the hierarchy is corrected downwards"""

        name = logger.name

        for child in obj.child_tree.keys():
            if child.parent is None:
                child.parent = logger
            elif not child.parent.name.startswith(name):
                if logger.parent is not child.parent:
                    logger.parent = child.parent
                child.parent = logger

    def _check_parents(self, logger: "Log"):
        """Ensure the hierarchy is corrected upwards"""

        name = logger.name
        parent = None
        parts = name.split(".")

        if len(parts) == 1:
            return
        _l = len(parts) - 1

        for idx in range(_l):
            sub = parts[0 : _l - idx]
            substr = ".".join(sub)

            if substr not in self.logger_tree:
                self.logger_tree[substr] = DummyLog(logger)
            else:
                obj = self.logger_tree[substr]
                if isinstance(obj, Log):
                    parent = obj
                    break
                else:
                    obj.add_to_chain(logger)

        logger.parent = parent
        if parent is not None:
            logger.log_level = parent.log_level

    def resolve_logger_tree(
        self,
        logger: "Log",
    ):
        """_summary_"""

        obj = None
        name = logger.name

        _Global_and_Destruct_Lock.acquire()
        if name in self.logger_tree:
            obj = self.logger_tree[name]
            if isinstance(obj, DummyLog):
                self.logger_tree[name] = logger
                self._check_children(obj, logger)
                self._check_parents(logger)
                obj = None
        else:
            self.logger_tree[name] = logger
            self._check_parents(logger)
        _Global_and_Destruct_Lock.release()

        return obj

    # def spawn_logger(self, name: str):
    #     """_summary_"""

    #     logger = None
    #     _Global_and_Destruct_Lock.acquire()

    #     if name in self.logger_tree:
    #         logger = self.logger_tree[name]
    #         if isinstance(logger, DummyLog):
    #             obj = logger
    #             logger = Log(name)
    #             self.logger_tree[name] = logger
    #             self._check_children(obj, logger)
    #             self._check_parents(logger)
    #     else:
    #         logger = Log(name)
    #         self._check_parents(logger)
    #         self.logger_tree[name] = logger
    #     _Global_and_Destruct_Lock.release()

    #     return logger


def spawn_logger(
    name: str,
) -> "Log":
    """Spawn a logger within a hierarchy

    Parameters
    ----------
    name : str
        _description_

    Returns
    -------
    Log
        _description_
    """

    return Log(name)


class Logmeta(type):
    def __call__(
        cls,
        name: str,
        log_level: int = 2,
    ):
        """overriding default calling behaviour to accommodete
        the check in the logger tree
        """

        obj = cls.__new__(cls, name, log_level)
        cls.__init__(obj, name, log_level)

        res = Log.manager.resolve_logger_tree(obj)
        if res is not None:
            warn(
                f"{name} is already in use -> returning currently known object",
                UserWarning,
            )
            obj = res

        return obj


class Log(metaclass=Logmeta):
    """Logger class"""

    manager = LogManager()

    def __init__(
        self,
        name: str,
        log_level: int = 2,
    ):
        """Logging!

        Parameters
        ----------
        name : str
            _description_
        log_level : int, optional
            _description_, by default 2
        """

        self._log_level = _Level(log_level)
        self.name = name
        self.bubble_up = True
        self.parent = None
        self._streams = []

        _loggers[self.name] = self

    def __del__(self):
        pass

    def __repr__(self):
        _lvl_str = str(LogLevels(self.log_level)).split(".")[1]
        return f"<Log {self.name} level={_lvl_str}>"

    def __str__(self):
        _mem_loc = f"{id(self):#018x}".upper()
        return f"<{self.__class__.__name__} object at {_mem_loc}>"

    def _log(self, item):
        """Handles logging"""

        obj = self
        while obj:
            for logger in obj._streams:
                if LogLevels[item.level].value < logger.level:
                    continue
                else:
                    logger.emit(str(item))
            if not obj.bubble_up:
                obj = None
            else:
                obj = obj.parent

    def handleLog(log_m):
        """A wrapper for logging messages"""

        def handle(self, *args, **kwargs):
            lvl, msg = log_m(self, *args, **kwargs)
            self._log(LogItem(level=lvl, msg=msg))

        return handle

    def add_cmd_stream(
        self,
        level: int = 2,
        name: str = None,
    ):
        """Add an outlet to the console

        Parameters
        ----------
        level : int, optional
            _description_, by default 2
        name : str, optional
            _description_, by default None
        """

        self._streams.append(CMDStream(level=level, name=name))

    def add_file_stream(
        self,
        dst: str,
        level: int = 2,
        filename: str = None,
    ):
        """Add an outlet to a file

        Parameters
        ----------
        dst : str
            _description_
        level : int, optional
            _description_, by default 2
        filename : str, optional
            _description_, by default None
        """

        self._streams.append(FileStream(dst=dst, level=level, name=filename))

    @property
    def log_level(self):
        return self._log_level

    @log_level.setter
    def log_level(
        self,
        val: int,
    ):
        self._log_level = _Level(val)

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


def setup_default_log(
    name: str,
    log_level: int,
    dst: str,
) -> Log:
    """_summary_

    Parameters
    ----------
    name : str
        _description_
    log_level : int
        _description_
    dst : str
        _description_

    Returns
    -------
    Log
        _description_

    Raises
    ------
    ValueError
        _description_
    """

    # Check if the name is valid
    if len(name.split(".")) > 1:
        raise ValueError()

    # Setup the logger
    obj = Log(name, log_level=log_level)

    # Add the streams
    obj.add_cmd_stream(level=log_level)
    obj.add_file_stream(
        dst,
        level=log_level,
        filename=name,
    )

    return obj
