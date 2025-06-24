"""Logging handlers."""

import atexit
import os
import sys
import threading
import weakref

from fiat.log.formatter import MessageFormatter
from fiat.log.util import (
    DEFAULT_FMT,
    DEFAULT_TIME_FMT,
    LogItem,
    check_loglevel,
    global_acquire,
    global_release,
)
from fiat.util import NOT_IMPLEMENTED

__all__ = ["CHandler", "FileHandler"]

STREAM_COUNT = 1

_default_formatter = MessageFormatter(DEFAULT_FMT, DEFAULT_TIME_FMT)
_handlers = weakref.WeakValueDictionary()


def _destruct_handlers():
    """Clean up at interpreter exit."""
    items = list(_handlers.items())
    for _, handler in items:
        handler.acquire()
        if not handler.stream.closed:
            handler.flush()
        handler.close()
        handler.release()


atexit.register(_destruct_handlers)


class BaseHandler:
    """Create base class for all stream handlers.

    Parameters
    ----------
    level : int, optional
        Logging level, by default 2 (INFO)
    """

    def __init__(
        self,
        level: int = 2,
    ):
        self.level = check_loglevel(level)
        self.msg_formatter = None
        self._name = None
        self._closed = False

        self._make_lock()

    def __repr__(self):
        _mem_loc = f"{id(self):#018x}".upper()
        return f"<{self.__class__.__name__} object at {_mem_loc}>"

    def _add_global_stream_ref(
        self,
    ):
        """Add a global reference for this handler."""
        global_acquire()
        _handlers[self._name] = self
        global_release()

    def _make_lock(self):
        """Create a lock."""
        self._lock = threading.RLock()

    def acquire(self):
        """Acquire the lock."""
        self._lock.acquire()

    def release(self):
        """Release the lock."""
        self._lock.release()

    def close(self):
        """Close and clean up."""
        global_acquire()
        self._closed = True
        del _handlers[self._name]
        global_release()

    def emit(self):
        """Emit a message."""
        raise NotImplementedError(NOT_IMPLEMENTED)

    def flush(self):
        """Flush."""
        raise NotImplementedError(NOT_IMPLEMENTED)

    def format(
        self,
        record: LogItem,
    ):
        """Format a record.

        Parameters
        ----------
        record : LogItem
            The records.

        Returns
        -------
        str
            Formatted record (message)
        """
        if self.msg_formatter:
            msg_fmt = self.msg_formatter
        else:
            msg_fmt = _default_formatter
        return msg_fmt.format(record)

    def set_formatter(
        self,
        formatter: MessageFormatter,
    ):
        """Set the message formatter.

        Parameters
        ----------
        formatter : MessageFormatter
            The formatter.
        """
        self.msg_formatter = formatter


class CHandler(BaseHandler):
    """Output text to the console.

    Parameters
    ----------
    level : int, optional
        Logging level, by default 2 (INFO)
    stream : type, optional
        Stream to which to send the logging messages.
        If none is provided, stdout is chosen. By default None
    name : str, optional
        Name of the added handler, by default None
    """

    def __init__(
        self,
        level: int = 2,
        stream: type = None,
        name: str = None,
    ):
        BaseHandler.__init__(self, level=level)

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

    def emit(self, record):
        """Emit a certain message."""
        msg = self.format(record)
        self.stream.write(msg)
        self.flush()

    def flush(self):
        """Dump cache to desired destination."""
        self.acquire()
        self.stream.flush()
        self.release()


class FileHandler(CHandler):
    """Output text to a file.

    Parameters
    ----------
    level : int
        Logging level.
    dst : str
        The destination of the logging (text) file.
    name : str, optional
        The name of the file handler, by default None
    mode : str, optional
        Mode in which to open the log file, by default 'w'
    """

    def __init__(
        self,
        level: int,
        dst: str,
        name: str = None,
        mode: str = "w",
    ):
        if name is None:
            name = "log_default"
        self._filename = os.path.join(dst, f"{name}.log")
        CHandler.__init__(self, level, self._open(mode), name)

    def _open(
        self,
        mode: str = "w",
    ):
        """Open a txt file and return the handler."""
        return open(self._filename, mode)

    def close(self):
        """Close and clean up."""
        self.acquire()
        self.flush()

        stream = self.stream
        self.stream = None

        stream.close()
        CHandler.close(self)
        self.release()
