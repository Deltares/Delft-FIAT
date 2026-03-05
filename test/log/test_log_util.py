import pytest

from fiat.log.util import LogItem, check_loglevel


def test_logitem():
    # Create a logging item
    l = LogItem(3, "A logging message")

    # Assert it's properties
    assert l.level == 3
    assert l.levelname == "WARNING"

    # Assert the message
    assert l.get_message() == "A logging message"


def test_check_loglevel():
    # Call the function with int input
    l = check_loglevel(2)

    # Assert the output
    assert l == 2  # Seems obvious

    # Call the function with string input
    l = check_loglevel("info")

    # Assert the output
    assert l == 2  # look at that


def test_check_loglevel_errors():
    # Call the function with int input
    with pytest.raises(ValueError, match=r"Level \(8\) is not a valid log level."):
        check_loglevel(8)

    # Call the function with string input
    with pytest.raises(
        ValueError, match=r"Level \(UNKNOWN\) is not a valid log level."
    ):
        check_loglevel("unknown")

    # Unknown type error
    with pytest.raises(
        TypeError, match=r"Level \(2.2\) of incorrect type -> type: float"
    ):
        check_loglevel(2.2)
