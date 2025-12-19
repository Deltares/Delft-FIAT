"""Typing for custom stuff."""

from typing import Callable, Protocol


class MethodsProtocol(Protocol):
    """Typing for methods module."""

    MANDATORY_COLUMNS: list
    MANDATORY_ENTRIES: list
    NEW_COLUMNS: list
    fn_hazard: Callable
    fn_impact: Callable
