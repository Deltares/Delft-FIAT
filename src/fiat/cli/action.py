"""Custom actions for cli."""

import argparse


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
            key_value_dict[key] = value
            setattr(namespace, self.dest, key_value_dict)
        except BaseException:
            parser.error(f"-d, key/ value pair in the wrong format: -> '{values}'. \
Should be KEY=VALUE")
