"""Quick setup function for logging."""

from fiat.log.formatter import MessageFormatter
from fiat.log.handler import FileHandler
from fiat.log.logger import Logger
from fiat.log.thread import Receiver

__all__ = ["setup_default_log", "setup_mp_log", "spawn_logger"]


def spawn_logger(
    name: str,
) -> Logger:
    """Spawn a logger within a hierarchy.

    Parameters
    ----------
    name : str
        The identifier of the logger.

    Returns
    -------
    Logger
        A Logger object (for logging).
    """
    return Logger(name)


def setup_default_log(
    name: str,
    level: int,
    dst: str | None = None,
) -> Logger:
    """Set up the base logger of a hierarchy.

    It's advisable to make this a single string that is not concatenated by period.
    E.g. 'fiat' is correct, 'fiat.logging' is not.

    Parameters
    ----------
    name : str
        Identifier of the logger.
    level : int
        Logging level.
    dst : str | None, optional
        The path to where the logging file will be located.

    Returns
    -------
    Logger
        A Logger object (for logging, no really..)
    """
    if len(name.split(".")) > 1:
        raise ValueError("Only root names (without a period) are allowed.")

    obj = Logger(name, level=level)

    obj.add_handler(level=level)
    if dst is not None:
        obj.add_file_handler(
            dst,
            level=level,
            filename=name,
        )

    return obj


def setup_mp_log(
    queue: object,
    name: str,
    level: int,
    dst: str = None,
):
    """Set up logging for multiprocessing.

    This essentially is a pipe back to the main Python process.

    Parameters
    ----------
    queue : queue.Queue
        A queue where the messages will be put in.
        N.B. this must be a multiprocessing queue, a normal queue.Queue \
will not suffice.
    name : str
        Identifier of the logger.
    level : int
        Logging level.
    dst : str, optional
        Destination of the logging. I.e. the path to the logging file.

    Returns
    -------
    Receiver
        A receiver object. This is the receiver of the pipeline.
    """
    obj = Receiver(queue)
    h = FileHandler(level=level, dst=dst, name=name)
    h.set_formatter(MessageFormatter("{asctime:20s}{message}"))
    obj.add_handler(h)
    return obj
