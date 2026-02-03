"""Logging with multithreading."""

from multiprocessing.queues import Queue

from fiat.log.handler import BaseHandler
from fiat.log.util import LogItem
from fiat.thread import Receiver, Sender

__all__ = ["LogReceiver", "LogSender"]


class LogSender(BaseHandler, Sender):
    """Sender object for records.

    Parameters
    ----------
    queue : object
        The queue for the records. Specifically designed for use in multiprocessing.
    """

    def __init__(self, queue: Queue):
        super().__init__(queue=queue)


class LogReceiver(Receiver):
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
        queue: Queue,
    ):
        super().__init__(queue=queue)
        self._handlers: list[BaseHandler] = []

    ## properties
    @property
    def closed(self):
        """Return the current state."""
        return self._closed

    ## I/O methods
    def close_handlers(self):
        """Close all associated handlers."""
        for handler in self._handlers:
            handler.close()
            handler = None

    ## Specific methods
    def add_handler(
        self,
        handler: BaseHandler,
    ):
        """Add a handler to the receiver.

        Parameters
        ----------
        handler : object
            A stream of some sorts.
        """
        self._handlers.append(handler)

    def fn(
        self,
        record: LogItem,
    ):
        """Log an item."""
        for handler in self._handlers:
            if record.level >= handler.level:
                handler.emit(record)
