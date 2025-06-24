import pytest

from fiat.log.util import LogItem


@pytest.fixture
def log_item() -> LogItem:
    l = LogItem(2, "A logging message")
    return l
