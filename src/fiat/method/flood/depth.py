"""Flood depth impact functions."""

import math
from typing import Callable

import numpy as np

from fiat._core import zonal_reduce
from fiat.method.util import ZONAL_CODES
from fiat.util import DEPTH, FLOOD_DEPTH

__all__ = ["fn_hazard", "fn_impact"]

COLUMNS = ["elevation"]
INDEX = DEPTH
NAME = FLOOD_DEPTH
NEW_COLUMNS = [DEPTH]
TYPES = [f"water_{DEPTH}"]


def fn_hazard(
    hazard: np.ndarray | list[float],
    elevation: float,
    method: str = "mean",
) -> tuple[float]:
    """Calculate the hazard value for flood depth hazard.

    Parameters
    ----------
    hazard : np.ndarray | list
        Raw hazard values.
    elevation : float
        Elevation of the object relative to the surface.
    method : str, optional
        Chose 'max' or 'mean' for either the maximum value or the average,
        by default 'mean'.

    Returns
    -------
    float
        A representative hazard value.
    """
    # Filter to positive values and reduce in one compiled pass.
    value, redf = zonal_reduce(
        np.ascontiguousarray(hazard, dtype=np.float64),
        ZONAL_CODES[method],
        0.0,
    )
    if math.isnan(value):
        return math.nan, math.nan
    return value - elevation, redf


def fn_impact(
    hazard: float | int,
    exposure: float | int,
    fn_curve: Callable,
    fact: float | int,
) -> float:
    """Calculate the impact from flood depths.

    Parameters
    ----------
    hazard : float | int
        The flood depth hazard values.
    exposure : float | int
        The maximum exposure impact (damage) value.
    fn_curve : Callable
        The vulnerability curve.
    fact : float | int
        The reduction factor (area method).

    Returns
    -------
    float
        Impact.
    """
    f = fn_curve(hazard)
    val = f * exposure * fact
    return val
