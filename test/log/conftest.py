import io
from multiprocessing import get_context
from multiprocessing.queues import Queue

import pytest

from fiat.log.formatter import MessageFormatter
from fiat.log.handler import StreamHandler
from fiat.log.util import LogItem


## Object for logging testing
@pytest.fixture
def log_item() -> LogItem:
    l = LogItem(2, "A logging message")
    return l


@pytest.fixture(scope="session")
def formatter() -> MessageFormatter:
    mf = MessageFormatter(fmt="{levelname:8s}{message}")
    return mf


@pytest.fixture
def mp_queue() -> Queue:
    ctx = get_context()
    q = Queue(ctx=ctx, maxsize=2)
    return q


@pytest.fixture
def stream_capture(log_capture: io.StringIO) -> StreamHandler:
    h = StreamHandler(level=2, stream=log_capture, name="stream")
    return h
