"""Theading objects."""

import atexit
import queue
import sys
import threading
import weakref
from multiprocessing.queues import Queue
from typing import Any, Callable

from fiat.util import FN

__all__ = ["Receiver", "Sender"]

RECEIVER_COUNT = 1
_global_lock = threading.RLock()
_receivers = weakref.WeakValueDictionary()


# For clearing out the receiver and joining the threads
def _destruct_receivers():
    """Clean up at interpreter exit."""
    items = list(_receivers.items())
    for _, receiver in items:
        receiver.close()


atexit.register(_destruct_receivers)


# Functions for global lock
def global_acquire():
    """Global method for acquiring global lock."""
    if _global_lock:
        _global_lock.acquire()


def global_release():
    """Global method for releasing global lock."""
    if _global_lock:
        _global_lock.release()


# The actual sender and receiver objects
class Sender:
    """Sender object for records.

    Parameters
    ----------
    queue : Queue
        The queue to submit records to.
    """

    def __init__(
        self,
        queue: Queue | queue.Queue,
    ):
        self.queue = queue

    def put(self, record: Any):
        """Put a record in the queue."""
        self.queue.put_nowait(record)

    def emit(self, record: Any):
        """Emit a record."""
        try:
            self.put(record)
        except BaseException:
            cdesc, _, _ = sys.exc_info()
            raise BufferError(f"Issue with the queue: {cdesc.__name__}")


class Receiver:
    """Create a receiver for queues.

    Essentially a listener.

    Parameters
    ----------
    queue : Queue
        A queue to retrieve the records from.
    """

    _sentinel = None

    def __init__(
        self,
        queue: Queue | queue.Queue,
    ):
        self._closed: bool = False
        self.count: int = 0
        self.queue: Queue = queue
        self.thread: threading.Thread | None = None

        # Set the name and add it to the registry
        global RECEIVER_COUNT
        self._name = f"Receiver{RECEIVER_COUNT}"
        RECEIVER_COUNT += 1
        self._add_global_receiver_ref()

    ## Private methods
    def _add_global_receiver_ref(self) -> None:
        """Add a global reference for the reciever."""
        global_acquire()
        _receivers[self._name] = self
        global_release()

    def _waiting(self, fn) -> None:
        """Wait for the next item/ record to be received."""
        while True:
            try:
                record = self.get(block=True)
                if record is self._sentinel:
                    break
                fn(record)
                self.count += 1
            except queue.Empty:
                break

    ## properties
    @property
    def closed(self) -> bool:
        """Return the current state."""
        return self._closed

    ## I/O methods
    def close(self) -> None:
        """Close the receiver."""
        if not self.closed:
            self.queue.put_nowait(self._sentinel)
            if self.thread is not None:
                self.thread.join()
            self.thread = None
            self._closed = True
        global_acquire()
        del _receivers[self._name]
        global_release()

    ## Specific methods
    def get(
        self,
        block: bool = True,
    ) -> Any:
        """Get something from the pipeline.

        Parameters
        ----------
        block : bool, optional
            If set to `True`, it will wait until it receives something.
        """
        return self.queue.get(block=block)

    def start(
        self,
        fn: Callable | None = None,
        name: str = "receiver",
    ) -> None:
        """Start the receiver.

        This will spawn a thread that manages the receiver.
        """
        fn_method = None
        if hasattr(self, FN):
            fn_method = getattr(self, FN)
        fn = fn or fn_method
        if fn is None:
            raise ValueError("fn not provided and object fn method not defined.")
        self.thread = t = threading.Thread(
            target=self._waiting,
            args=(fn,),
            name=name,
            daemon=True,
        )
        t.start()
