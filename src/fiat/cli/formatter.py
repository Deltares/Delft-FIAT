"""Formatter for the cli."""

from argparse import PARSER, Action, HelpFormatter, _MutuallyExclusiveGroup
from collections.abc import Iterable


class MainHelpFormatter(HelpFormatter):
    """_summary_."""

    def add_usage(
        self,
        usage: str | None,
        actions: Iterable[Action],
        groups: Iterable[_MutuallyExclusiveGroup],
        prefix: str | None = None,
    ) -> None:
        """_summary_."""
        return super().add_usage(usage, actions, groups, prefix)

    # def _format_usage(self, usage: str | None, actions: Iterable[Action],
    # groups: Iterable[_MutuallyExclusiveGroup], prefix: str | None) -> str:
    #     print(usage)
    #     return super()._format_usage(usage, actions, groups, prefix)

    def _format_action(self, action):
        parts = super()._format_action(action)
        if action.nargs == PARSER:
            parts = "\n".join(parts.split("\n")[1:])
        return parts

    def start_section(self, heading):
        """_summary_."""
        heading = heading[0].upper() + heading[1:]
        return super().start_section(heading)
