"""Typing for custom stuff."""

from types import ModuleType
from typing import Callable


class MethodType(ModuleType):
    """Typing for methods module."""

    COLUMNS: list[str]
    INDEX: str
    NAME: str
    NEW_COLUMNS: list[str]
    TYPES: list[str]
    fn_hazard: Callable[[list[float], str], tuple[float]]
    fn_impact: Callable[[float, float, Callable[[float], float], float], float]
