"""Logging objects."""

import weakref
from warnings import warn

from fiat.log.handler import CHandler, FileHandler
from fiat.log.util import (
    LogItem,
    LogLevels,
    check_loglevel,
    global_acquire,
    global_release,
)
from fiat.util import NOT_IMPLEMENTED

__all__ = ["Logger"]

_loggers = weakref.WeakValueDictionary()


class DummyLog:
    """Create dummy class for tracking children.

    (actually funny..).
    """

    def __init__(
        self,
        obj,
    ):
        self.child_tree = {obj: None}

    def __repr__(self):
        _mem_loc = f"{id(self):#018x}".upper()
        return f"<{self.__class__.__name__} object at {_mem_loc}>"

    def _check_succession(
        self,
        obj,
    ):
        """Remove child if older one is present."""
        _disinherit = [
            child for child in self.child_tree if child.name.startswith(obj.name)
        ]

        for child in _disinherit:
            del self.child_tree[child]

    def add_to_chain(self, obj):
        """Add object to the tree."""
        self._check_succession(obj)
        self.child_tree[obj] = None


class Logmeta(type):
    """Meta class for logging."""

    def __call__(
        cls,
        name: str,
        level: int = 2,
    ):
        """Override default calling behaviour.

        To accommodate the check in the logger tree.
        """
        obj = cls.__new__(cls, name, level)
        cls.__init__(obj, name, level)

        res = obj.manager.resolve_logger_tree(obj)
        if res is not None:
            warn(
                f"{name} is already in use -> returning currently known object",
                UserWarning,
            )
            obj = res

        return obj


class LogManager:
    """The manager of all the loggers."""

    def __init__(
        self,
    ):
        self.logger_tree = {}

    def _check_children(
        self,
        obj: DummyLog,
        logger: "Logger",
    ):
        """Ensure the hierarchy is corrected downwards."""
        name = logger.name

        for child in obj.child_tree.keys():
            if child.parent is None:
                child.parent = logger
            elif not child.parent.name.startswith(name):
                if logger.parent is not child.parent:
                    logger.parent = child.parent
                child.parent = logger

    def _check_parents(self, logger: "Logger"):
        """Ensure the hierarchy is corrected upwards."""
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
                if isinstance(obj, Logger):
                    parent = obj
                    break
                else:
                    obj.add_to_chain(logger)

        logger.parent = parent
        if parent is not None:
            logger.level = parent.level

    def resolve_logger_tree(
        self,
        logger: "Logger",
    ):
        """Solve the logger family tree."""
        obj = None
        name = logger.name

        global_acquire()
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
        global_release()

        return obj


class Logger(metaclass=Logmeta):
    """Generate a logger.

    The list of available logging levels:\n
    - 1: debug
    - 2: info
    - 3: warning
    - 4: error
    - 5: dead

    Parameters
    ----------
    name : str
        Logger identifier
    level : int, optional
        Level of the logger. Anything below this level will not be logged.
        For instance, a logging level of `2` (info) will result in all debug messages
        being muted.
    """

    manager = LogManager()

    # def __new__(
    #     cls,
    #     name: str,
    #     level: int = 2,
    # ):

    #     obj = object.__new__(cls)
    #     obj.__init__(name, level)

    #     res = Log.manager.fit_external_logger(obj)
    #     if res is not None:
    #         warn(f"{name} is already in use -> \
    # returning currently known object", UserWarning)
    #         obj = res

    #     return obj

    def __init__(
        self,
        name: str,
        level: int = 2,
    ):
        self._level = check_loglevel(level)
        self.name = name
        self.bubble_up = True
        self.parent = None
        self._handlers = []

        _loggers[self.name] = self

    def __del__(self):
        pass

    def __repr__(self):
        _lvl_str = str(LogLevels(self.level)).split(".")[1]
        return f"<Logger {self.name} level={_lvl_str}>"

    def __str__(self):
        _mem_loc = f"{id(self):#018x}".upper()
        return f"<{self.__class__.__name__} object at {_mem_loc}>"

    def _log(self, record):
        """Handle logging."""
        obj = self
        while obj:
            for handler in obj._handlers:
                if record.level < handler.level:
                    continue
                else:
                    handler.emit(record)
            if not obj.bubble_up:
                obj = None
            else:
                obj = obj.parent

    def _handle_log(log_m):
        """Wrap logging messages."""

        def handle(self, *args, **kwargs):
            lvl, msg = log_m(self, *args, **kwargs)
            self._log(LogItem(level=lvl, msg=msg))

        return handle

    def add_handler(
        self,
        level: int = 2,
        name: str = None,
        stream: type = None,
    ):
        """Add an outlet to the logging object.

        Parameters
        ----------
        level : int, optional
            Logging level, by default 2 (INFO)
        name : str, optional
            Name of the added handler, by default None
        stream : type, optional
            Stream to which to send the logging messages.
            If none is provided, stdout is chosen. By default None
        """
        self._handlers.append(CHandler(level=level, name=name, stream=stream))

    def add_file_handler(
        self,
        dst: str,
        level: int = 2,
        filename: str = None,
    ):
        """Add an outlet directed to a file.

        Parameters
        ----------
        dst : str
            The destination of the file, i.e. the path.
        level : int, optional
            Logging level.
        filename : str, optional
            The name of the file, also the identifier for the stream handler.
        """
        self._handlers.append(FileHandler(dst=dst, level=level, name=filename))

    @property
    def level(self):
        """Return the current logging level."""
        return self._level

    @level.setter
    def level(
        self,
        val: int,
    ):
        self._level = check_loglevel(val)
        for h in self._handlers:
            h.level = val

    def _direct(self, msg):
        """Log something directly."""
        raise NotImplementedError(NOT_IMPLEMENTED)

    @_handle_log
    def debug(self, msg: str):
        """Create a debug message."""
        return 1, msg

    @_handle_log
    def info(self, msg: str):
        """Create an info message."""
        return 2, msg

    @_handle_log
    def warning(self, msg: str):
        """Create a warning message."""
        return 3, msg

    @_handle_log
    def error(self, msg: str):
        """Create an error message."""
        return 4, msg

    @_handle_log
    def dead(self, msg: str):
        """Create a kernel-deceased message."""
        return 5, msg
