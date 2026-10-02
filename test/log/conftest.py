import io

import pytest

from fiat.log.formatter import MessageFormatter
from fiat.log.handler import StreamHandler
from fiat.log.util import FormatItem, LogItem


## Object for logging testing
@pytest.fixture
def format_item() -> FormatItem:
    f = FormatItem(levelname="INFO", message="A logging message")
    return f


@pytest.fixture
def log_item() -> LogItem:
    l = LogItem(2, "A logging message")
    return l


@pytest.fixture(scope="session")
def formatter() -> MessageFormatter:
    mf = MessageFormatter(fmt="{levelname:8s}{message}")
    return mf


@pytest.fixture
def stream_capture(log_buffer: io.StringIO) -> StreamHandler:
    h = StreamHandler(level=2, stream=log_buffer, name="stream")
    return h
