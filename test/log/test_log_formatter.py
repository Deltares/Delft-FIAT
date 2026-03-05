import datetime

import pytest

from fiat.log.formatter import FormatStyler, MessageFormatter
from fiat.log.util import LogItem


def test_formatstyler():
    # Create the object
    fs = FormatStyler("{asctime:20s}{levelname:8s}")

    # Assert some simple stuff
    assert fs.uses_time()
    assert fs._defaults is None

    # It's a valid pattern, so the validation should pass
    fs.validate()


def test_formatstyler_validate_errors():
    # Invalid field name, e.g. with a dash in there
    fs = FormatStyler("{invalid-field}")
    with pytest.raises(
        ValueError,
        match="Invalid format -> invalid field name/expression: invalid-field",
    ):
        fs.validate()

    # Invalid spec for formatting, e.g. 'm'
    fs = FormatStyler("{field:8m}")
    with pytest.raises(ValueError, match="Invalid format -> bad specifier: 8m"):
        fs.validate()

    # No fields found
    fs = FormatStyler("field")
    with pytest.raises(ValueError, match="Invalid format: no fields"):
        fs.validate()


def test_formatstyle_format(log_item: LogItem):
    # Create the object
    fs = FormatStyler("{levelname:8s}")

    # Call the format method
    msg = fs.format(log_item)

    # Assert the output
    assert msg == "INFO    "  # Note 4 spaces due to the '8s' spec


def test_formatstyle_format_defaults(log_item: LogItem):
    # Create the object
    fs = FormatStyler("{levelname:8s}{foo}", defaults={"foo": "bar"})

    # Call the format method
    msg = fs.format(log_item)

    # Assert the output
    assert msg == "INFO    bar"  # Note that foo is taken from the default
    # It's not in the record


def test_formatstyle_format_errors(log_item: LogItem):
    # Create the object
    fs = FormatStyler("{levelname:8s}{foo}")

    # Call the format method, which should result in an error
    with pytest.raises(ValueError, match="Formatting field not found in record: 'foo'"):
        _ = fs.format(log_item)


def test_messageformatter():
    # Create the object
    mf = MessageFormatter("{levelname:8s}")

    # Assert some simple stuff
    assert mf.fmt == "{levelname:8s}"
    assert mf.datefmt is None


def test_messageformatter_format(log_item: LogItem):
    # Create the object
    mf = MessageFormatter("{levelname:8s}")

    # Format the message
    msg = mf.format(log_item)
    # Assert the output
    assert msg == "INFO    \n"  # This formatter adds a newline char for proper logging

    # Add the message to the mix
    mf = MessageFormatter("{levelname:8s}{message}")

    # Format the message
    msg = mf.format(log_item)

    # Assert the output
    assert msg == "INFO    A logging message\n"  # Look a message


def test_messageformatter_format_time(log_item: LogItem):
    # Set date format
    datefmt = "%Y-%m-%d"
    # Create the object
    mf = MessageFormatter("{asctime:20s}{levelname:8s}")

    # Format the time
    t = mf.format_time(log_item)
    # Assert the output, i.e. current date in the formatted message
    assert datetime.datetime.now().strftime(datefmt) in t

    # Create a message with the datetime in it
    msg = mf.format(log_item)
    # Assert the output
    assert datetime.datetime.now().strftime(datefmt) in msg
    assert msg.endswith("INFO    \n")
