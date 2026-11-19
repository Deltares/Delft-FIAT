"""Flood depth impact functions."""

import math
from typing import Callable

import numpy as np

from fiat._core import zonal_reduce
from fiat.method.util import ZONAL_CODES
from fiat.util import DEPTH, FLOOD_DEPTH

__all__ = ["fn_hazard", "fn_impact"]

COLUMNS = ["elevation"]
NAME = FLOOD_DEPTH
NDATASETS = 1
NEW_COLUMNS = [DEPTH]
TYPES = [f"water_{DEPTH}"]
AXIS_TYPES = TYPES


def fn_hazard(
    hazards: tuple[np.ndarray, ...],
    elevation: float,
    method: str = "mean",
) -> tuple[tuple[float, ...], float]:
    """Calculate the hazard value for flood depth hazard.

    Parameters
    ----------
    hazards : tuple[np.ndarray, ...]
        Raw hazard values, one array (water depth).
    elevation : float
        Elevation of the object relative to the surface.
    method : str, optional
        Chose 'max', 'mean' or 'min' for the maximum, average or minimum value,
        by default 'mean'.

    Returns
    -------
    tuple[tuple[float, ...], float]
        The representative hazard value(s) and the reduction factor.
    """
    # Filter to positive values and reduce in one compiled pass.
    value, redf = zonal_reduce(
        np.ascontiguousarray(hazards[0], dtype=np.float64),
        ZONAL_CODES[method],
        0.0,
    )
    if math.isnan(value):
        return (math.nan,), math.nan
    return (value - elevation,), redf


def fn_impact(
    hazards: tuple[float | np.ndarray, ...],
    exposure: float | np.ndarray,
    curves: tuple[Callable[..., float | np.ndarray], ...],
    fact: float,
) -> float | np.ndarray:
    """Calculate the impact from flood depths.

    Works on scalars (geometries) as well as on arrays (grid cells).

    Parameters
    ----------
    hazards : tuple[float | np.ndarray, ...]
        The flood depth hazard values.
    exposure : float | np.ndarray
        The maximum exposure impact (damage) value.
    curves : tuple[Callable, ...]
        The vulnerability curve (one).
    fact : float
        The reduction factor (area method).

    Returns
    -------
    float | np.ndarray
        Impact.
    """
    return curves[0](hazards[0]) * exposure * fact
