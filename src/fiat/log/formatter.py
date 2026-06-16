"""Logging formatting."""

import re
import time
from string import Formatter as StrFormatter
from typing import Any

from fiat.log.util import DEFAULT_TIME_FMT, FormatItem, LogItem

__all__ = ["FormatStyler", "MessageFormatter"]

_str_formatter = StrFormatter()
del StrFormatter


class FormatStyler:
    """The underlying engine of the formatter.

    Parameters
    ----------
    fmt : str
        The format of the message.
    defaults : dict, optional
        Default values, by default None.
    """

    default_format: str = "{message}"
    asctime_format: str = "{asctime}"
    asctime_search: str = "{asctime"

    fmt_spec = re.compile(
        r"^(.?[<>=^])?[+ -]?#?0?(\d+|{\w+})?[,_]?(\.(\d+|{\w+}))?[bcdefgnosx%]?$", re.I
    )
    field_spec = re.compile(r"^(\d+|\w+)(\.\w+|\[[^]]+\])*$")

    def __init__(self, fmt: str | None, *, defaults: dict[str, Any] | None = None):
        self._fmt = fmt or self.default_format
        self._defaults = defaults

    def uses_time(self) -> bool:
        """Check if time is used in the formatter."""
        return self._fmt.find(self.asctime_search) >= 0

    def validate(self) -> None:
        """Validate the input format, ensure correct string formatting style."""
        fields = set()
        try:
            for _, fieldname, spec, _ in _str_formatter.parse(self._fmt):
                if fieldname:
                    if not self.field_spec.match(fieldname):
                        raise ValueError(f"invalid field name/expression: {fieldname}")
                    fields.add(fieldname)
                if spec and not self.fmt_spec.match(spec):
                    raise ValueError(f"bad specifier: {spec}")
        except ValueError as e:
            raise ValueError(f"Invalid format -> {e}")
        if not fields:
            raise ValueError("Invalid format: no fields")

    def _format(self, record: FormatItem) -> str:
        if defaults := self._defaults:
            values = defaults | record.__dict__
        else:
            values = record.__dict__
        return self._fmt.format(**values)

    def format(self, record: FormatItem) -> str:
        """Format the record."""
        try:
            return self._format(record)
        except KeyError as e:
            raise ValueError(f"Formatting field not found in record: {e}")


class MessageFormatter:
    """Format logging items.

    Parameters
    ----------
    fmt : str, optional
        The format, by default None.
    datefmt : str, optional
        The date(time) format, by default None.
    validate : bool, optional
        Validate the supplied formats, by default True.
    defaults : dict, optional
        Default values, by default None.
    """

    def __init__(
        self,
        fmt: str | None = None,
        datefmt: str | None = None,
        validate: bool = True,
        *,
        defaults: dict[str, Any] | None = None,
    ):
        self.style = FormatStyler(fmt, defaults=defaults)
        if validate:
            self.style.validate()

        self.datefmt = datefmt

    ## Properties
    @property
    def fmt(self) -> str:
        """Return the string format."""
        return self.style._fmt

    ## Executing methods
    def format_time(self, record: LogItem) -> str:
        """Format the time."""
        ct = time.localtime(record.ct)
        if datefmt := self.datefmt:
            s = time.strftime(datefmt, ct)
        else:
            s = time.strftime(DEFAULT_TIME_FMT, ct)
        return s

    def format(self, record: LogItem) -> str:
        """Format a record.

        Parameters
        ----------
        record : LogItem
            The record to be formatted.

        Returns
        -------
        str
            Formatted record/ message.
        """
        item = FormatItem(
            levelname=record.get_levelname(),
            message=record.get_message(),
        )
        if self.style.uses_time():
            item.asctime = self.format_time(record)
        s = self.style.format(item)
        if not s.endswith("\n"):
            s = s + "\n"
        return s
