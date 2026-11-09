"""Flood depth and duration impact functions (combined datasets)."""

import math
from typing import Callable

import numpy as np

from fiat._core import zonal_reduce
from fiat.method.util import ZONAL_CODES
from fiat.util import DEPTH, DURATION, FLOOD_DEPTH_DURATION

__all__ = ["fn_hazard", "fn_impact"]

_REDUCERS: dict[str, Callable[[np.ndarray], float]] = {
    "max": np.max,
    "mean": np.mean,
    "min": np.min,
}

COLUMNS = ["elevation"]
NAME = FLOOD_DEPTH_DURATION
NDATASETS = 2
NEW_COLUMNS = [DEPTH, DURATION]
TYPES = [f"water_{DEPTH}", DURATION]
AXIS_TYPES = TYPES


def fn_hazard(
    hazards: tuple[np.ndarray, ...],
    elevation: float,
    method: str = "mean",
) -> tuple[tuple[float, ...], float]:
    """Calculate the hazard values for flood depth and duration hazard.

    Parameters
    ----------
    hazards : tuple[np.ndarray, ...]
        Raw hazard values, two arrays (water depth and flood duration).
    elevation : float
        Elevation of the object relative to the surface.
    method : str, optional
        Chose 'max', 'mean' or 'min' for the maximum, average or minimum value,
        by default 'mean'.

    Returns
    -------
    tuple[tuple[float, ...], float]
        The representative depth and duration and the reduction factor
        (derived from the depth). The duration is reduced over the wet pixels
        (depth > 0) and is nan when it holds nodata on any of them.
    """
    depths = np.ascontiguousarray(hazards[0], dtype=np.float64)
    depth, redf = zonal_reduce(depths, ZONAL_CODES[method], 0.0)
    if math.isnan(depth):
        return (math.nan, math.nan), math.nan
    # Reduce the duration over the wet pixels, zero durations included.
    durations = np.asarray(hazards[1], dtype=np.float64)[depths > 0.0]
    duration = float(_REDUCERS[method](durations))
    return (depth - elevation, duration), redf


def fn_impact(
    hazards: tuple[float | np.ndarray, ...],
    exposure: float | np.ndarray,
    curves: tuple[Callable[..., float | np.ndarray], ...],
    fact: float,
) -> float | np.ndarray:
    """Calculate the impact from flood depths and durations.

    The direct (depth) and indirect (duration) curve factors are multiplied.
    Works on scalars (geometries) as well as on arrays (grid cells).

    Parameters
    ----------
    hazards : tuple[float | np.ndarray, ...]
        The flood depth and flood duration hazard values.
    exposure : float | np.ndarray
        The maximum exposure impact (damage) value.
    curves : tuple[Callable, ...]
        The depth and the duration vulnerability curve.
    fact : float
        The reduction factor (area method).

    Returns
    -------
    float | np.ndarray
        Impact.
    """
    return curves[0](hazards[0]) * curves[1](hazards[1]) * exposure * fact
