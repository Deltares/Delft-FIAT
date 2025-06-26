"""Logging objects."""

import weakref
from warnings import warn

from fiat.log.handler import FileHandler, StreamHandler
from fiat.log.util import (
    LogItem,
    LogLevels,
    check_loglevel,
    global_acquire,
    global_release,
)

__all__ = ["Logger"]

_loggers = weakref.WeakValueDictionary()


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
        obj: Logger = cls.__new__(cls, name, level)
        cls.__init__(obj, name, level)

        res = obj.manager.resolve_logger_tree(obj)
        if res is not None:
            warn(
                f"{name} is already in use -> returning currently known object",
                UserWarning,
            )
            obj = res

        return obj


class BaseLogger:
    """Create dummy class for tracking children.

    (actually funny..).
    """

    def __init__(
        self,
    ):
        self.children = weakref.WeakValueDictionary()

    def __repr__(self):
        _mem_loc = f"{id(self):#018x}".upper()
        return f"<{self.__class__.__name__} object at {_mem_loc}>"

    ## Private methods
    def _check_succession(
        self,
        obj: "Logger",
    ):
        """Remove child if older one is present."""
        _disinherit = [child for child in self.children if child.startswith(obj.name)]

        for child in _disinherit:
            _ = self.children.pop(child)

    ## Mutating methods
    def add_child(self, obj: "Logger"):
        """Add object to the tree."""
        self._check_succession(obj)
        self.children[obj.name] = obj


class LogManager:
    """The manager of all the loggers."""

    def __init__(
        self,
    ):
        self.logger_tree = {}

    ## Private methods
    def _check_children(
        self,
        obj: BaseLogger,
        logger: "Logger",
    ):
        """Ensure the hierarchy is corrected downwards."""
        for child in obj.children.values():
            if logger.parent is not child.parent:
                logger.parent = child.parent
            child.parent = logger
            logger.add_child(child)

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
                obj = BaseLogger()
                self.logger_tree[substr] = obj
            else:
                obj = self.logger_tree[substr]
                if isinstance(obj, Logger):
                    parent = obj
                    break
            obj.add_child(logger)

        logger.parent = parent
        if parent is not None:
            parent.add_child(logger)
            logger.level = parent.level

    ## Resolve method
    def resolve_logger_tree(
        self,
        logger: "Logger",
    ):
        """Solve the logger family tree."""
        obj = None
        name = logger.name

        # Acquire
        global_acquire()

        # Solve the family tree
        if name in self.logger_tree:
            obj = self.logger_tree[name]
            if not isinstance(obj, Logger):
                self.logger_tree[name] = logger
                self._check_children(obj, logger)
                obj = None
        else:
            self.logger_tree[name] = logger
        self._check_parents(logger)

        # Release
        global_release()

        # Return the object or NoneType
        return obj


class Logger(BaseLogger, metaclass=Logmeta):
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

    def __init__(
        self,
        name: str,
        level: int = 2,
    ):
        self._level = check_loglevel(level)
        BaseLogger.__init__(self)
        self.name = name
        self.bubble_up = True
        self.parent = None
        self._handlers = []

        _loggers[self.name] = self

    def __del__(self):
        pass

    def __repr__(self):
        _mem_loc = f"{id(self):#018x}".upper()
        _lvl_str = LogLevels(self.level).name
        return f"<Logger {self.name} level={_lvl_str} at {_mem_loc}>"

    ## Private methods/ decorators
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

    ## Properties
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

    ## Mutating methods
    def add_stream_handler(
        self,
        level: int = 2,
        name: str | None = None,
        stream: type | None = None,
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
        self._handlers.append(StreamHandler(level=level, name=name, stream=stream))

    def add_file_handler(
        self,
        level: int = 2,
        dst: str | None = None,
        filename: str | None = None,
    ):
        """Add an outlet directed to a file.

        If not destination is provided, the file is placed in the current working
        directory.

        Parameters
        ----------
        level : int, optional
            Logging level. By default 2 (INFO)
        dst : str
            The destination of the file, i.e. the path. By default None (cwd)
        filename : str, optional
            The name of the file, also the identifier for the stream handler.
        """
        self._handlers.append(FileHandler(dst=dst, level=level, name=filename))

    ## Logging methods
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
