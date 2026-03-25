"""Flood depth impact functions."""

import math
from typing import Callable

from fiat.method.util import ZONAL_METHODS
from fiat.util import DEPTH, FLOOD_DEPTH

COLUMNS = ["elevation"]
INDEX = DEPTH
NAME = FLOOD_DEPTH
NEW_COLUMNS = [DEPTH]
TYPES = [f"water_{DEPTH}"]


def fn_hazard(
    hazard: list[float],
    elevation: float,
    method: str = "mean",
) -> tuple[float]:
    """Calculate the hazard value for flood depth hazard.

    Parameters
    ----------
    hazard : list
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
    # Remove the negative hazard values to 0.
    raw_l = len(hazard)
    hazard = [n for n in hazard if n > 0]
    if not hazard:
        return math.nan, math.nan
    redf = len(hazard) / raw_l
    hazard = ZONAL_METHODS[method](hazard) - elevation
    return hazard, redf


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
