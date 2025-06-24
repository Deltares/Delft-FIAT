"""Logging with multithreading."""

import atexit
import queue
import threading
import weakref

from fiat.log.handler import BaseHandler
from fiat.log.util import LogItem, global_acquire, global_release

__all__ = ["Receiver", "Sender"]

RECEIVER_COUNT = 1

_receivers = weakref.WeakValueDictionary()


def _destruct_receivers():
    """Clean up at interpreter exit."""
    items = list(_receivers.items())
    for _, receiver in items:
        receiver.close()


atexit.register(_destruct_receivers)


class Sender(BaseHandler):
    """Sender object for records.

    Parameters
    ----------
    queue : object
        The queue for the records. Specifically designed for use in multiprocessing.
    """

    def __init__(self, queue: object):
        BaseHandler.__init__(self)
        self.q = queue

    def put(self, record):
        """Put a record in the queue."""
        self.q.put_nowait(record)

    def emit(self, record):
        """Emit a record."""
        try:
            self.put(record)
        except Exception:
            self.handleError(record)


class Receiver:
    """Create a receiver for multiprocessing logging.

    Essentially a listener.

    Parameters
    ----------
    queue : object
        A queue for putting the messages in. This has to be a designated
        multiprocessing object.
    """

    _sentinel = None

    def __init__(
        self,
        queue: object,
    ):
        self._closed = False
        self._t = None
        self._handlers = []
        self.count = 0
        self.q = queue

        global RECEIVER_COUNT
        self._name = f"Receiver{RECEIVER_COUNT}"
        RECEIVER_COUNT += 1

        self._add_global_receiver_ref()

    def _add_global_receiver_ref(
        self,
    ):
        """Add a global reference for the reciever."""
        global_acquire()
        _receivers[self._name] = self
        global_release()

    def _log(
        self,
        record: LogItem,
    ):
        """Log an item."""
        for handler in self._handlers:
            if record.level >= handler.level:
                handler.emit(record)

    def _waiting(self):
        """Wait for the next item/ record to be received."""
        while True:
            try:
                record = self.get(True)
                if record is self._sentinel:
                    break
                self._log(record)
                self.count += 1
            except queue.Empty:
                break

    def close(self):
        """Close the receiver."""
        if not self._closed:
            self.q.put_nowait(self._sentinel)
            self._t.join()
            self._t = None
            self._closed = True
        global_acquire()
        del _receivers[self._name]
        global_release()

    def close_handlers(self):
        """Close all associated handlers."""
        for handler in self._handlers:
            handler.close()
            handler = None

    def get(
        self,
        block: bool = True,
    ):
        """Get something from the pipeline.

        Parameters
        ----------
        block : bool, optional
            If set to `True`, it will wait until it receives something.
        """
        return self.q.get(block=block)

    def add_handler(
        self,
        handler: object,
    ):
        """Add a handler to the receiver.

        Parameters
        ----------
        handler : object
            A stream of some sorts.
        """
        self._handlers.append(handler)

    def start(self):
        """Start the receiver.

        This will spawn a thread that manages the receiver.
        """
        self._t = t = threading.Thread(
            target=self._waiting,
            name="mp_logging_thread",
            daemon=True,
        )
        t.start()
