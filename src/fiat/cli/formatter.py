"""Formatter for the cli."""

from argparse import PARSER, Action, HelpFormatter, _MutuallyExclusiveGroup
from collections.abc import Iterable


class MainHelpFormatter(HelpFormatter):
    """Format the help screen over cli."""

    def __init__(self, *args, **kwargs):
        kwargs["max_help_position"] = 40
        super().__init__(*args, **kwargs)

    def add_usage(
        self,
        usage: str | None,
        actions: Iterable[Action],
        groups: Iterable[_MutuallyExclusiveGroup],
        prefix: str | None = None,
    ) -> None:
        """Add usage string."""
        return super().add_usage(usage, actions, groups, prefix)

    def _format_action_invocation(self, action):
        if not action.option_strings:
            return super()._format_action_invocation(action)
        else:
            default = self._get_default_metavar_for_optional(action)
            metavar = self._format_args(action, default)
            # help_string = self._get_help_string(action)
            return ", ".join(action.option_strings) + " " + metavar

    def _format_action(self, action):
        parts = super()._format_action(action)
        if action.nargs == PARSER:
            parts = "\n".join(parts.split("\n")[1:])
        return parts

    def _format_usage(self, usage, actions, groups, prefix):
        if prefix is None:
            prefix = "Usage: "

        # Program name
        usage_args = [self._prog]

        # Add options string if there are actions (options)
        if actions:
            usage_args.append("<options>")

        # Positional arguments
        positionals = [
            action.metavar or action.dest
            for action in actions
            if action.option_strings == []
        ]
        usage_args.extend(positionals)

        # Return the formatted string
        return f"{prefix}{' '.join(usage_args)}\n"

    def start_section(self, heading):
        """Show start section."""
        heading = heading[0].upper() + heading[1:]
        return super().start_section(heading)
