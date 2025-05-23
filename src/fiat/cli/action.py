"""Custom actions for cli."""

import argparse
import re

from fiat.util import _dtypes_reversed, deter_type


def parse_cli_value(value: str) -> object:
    """Parse the value to a python type."""
    value = value.strip()
    m = re.findall(r"^\[(.*)\]$", value)  # Pattern for checking list
    # If not a list, then it's a single value
    if len(m) == 0:
        t = deter_type(value.encode(), 0)
        value = _dtypes_reversed[t](value)
        return value

    # If it's a list
    item = m[0]
    item = item.replace(" ", "")  # Strip it from spaces
    # Detemine the type of the list and use that to set the types of the elements
    t = deter_type(item.replace(",", "\n").encode(), item.count(","))
    value = [_dtypes_reversed[t](elem) for elem in item.split(",")]
    return value


class KeyValueAction(argparse.Action):
    """Simple class for key values pairs with equal signs."""

    def __call__(self, parser, namespace, values, option_string=None):
        """Overwrite call method."""
        # Check for existence
        if getattr(namespace, self.dest) is None:
            setattr(namespace, self.dest, {})

        # Set the values
        try:
            key_value_dict = getattr(namespace, self.dest)
            key, value = values.split("=", 1)
            key_value_dict[key] = parse_cli_value(value)
            setattr(namespace, self.dest, key_value_dict)
        except BaseException:
            parser.error(f"-d, key/ value pair in the wrong format: -> '{values}'. \
Should be KEY=VALUE")
