"""Typing for custom stuff."""

from types import ModuleType
from typing import Callable

import numpy as np


class MethodType(ModuleType):
    """Typing for methods module."""

    AXIS_TYPES: list[str]
    COLUMNS: list[str]
    NAME: str
    NDATASETS: int
    NEW_COLUMNS: list[str]
    TYPES: list[str]
    fn_hazard: Callable[..., tuple[tuple[float, ...], float]]
    fn_impact: Callable[..., float | np.ndarray]
