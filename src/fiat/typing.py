"""Typing for custom stuff."""

from typing import Callable, Protocol


class MethodsProtocol(Protocol):
    """Typing for methods module."""

    COLUMNS: list[str]
    NAME: str
    NEW_COLUMNS: list[str]
    TYPES: list[str]
    fn_hazard: Callable
    fn_impact: Callable
