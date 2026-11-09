"""Flood depth and duration impact functions (one 2D dataset)."""

from typing import Callable

import numpy as np

from fiat.method.flood.depth_duration import COLUMNS as COLUMNS
from fiat.method.flood.depth_duration import NEW_COLUMNS as NEW_COLUMNS
from fiat.method.flood.depth_duration import TYPES as TYPES
from fiat.method.flood.depth_duration import fn_hazard as fn_hazard
from fiat.util import FLOOD_DEPTH_DURATION_2D

__all__ = ["fn_hazard", "fn_impact"]

NAME = FLOOD_DEPTH_DURATION_2D
NDATASETS = 1
AXIS_TYPES = TYPES


def fn_impact(
    hazards: tuple[float | np.ndarray, ...],
    exposure: float | np.ndarray,
    curves: tuple[Callable[..., float | np.ndarray], ...],
    fact: float,
) -> float | np.ndarray:
    """Calculate the impact from flood depths and durations on a 2D curve.

    Works on scalars (geometries) as well as on arrays (grid cells).

    Parameters
    ----------
    hazards : tuple[float | np.ndarray, ...]
        The flood depth and flood duration hazard values.
    exposure : float | np.ndarray
        The maximum exposure impact (damage) value.
    curves : tuple[Callable, ...]
        The 2D (depth, duration) vulnerability curve (one).
    fact : float
        The reduction factor (area method).

    Returns
    -------
    float | np.ndarray
        Impact.
    """
    return curves[0](hazards[0], hazards[1]) * exposure * fact
