"""Functions specifically for flood risk calculation."""

import math
from typing import Callable

from fiat.method.util import AREA_METHODS

COLUMNS = ["ref"]
NAME = "flood"
NEW_COLUMNS = ["depth"]
TYPES = ["water_depth"]


def fn_hazard(
    hazard: list,
    ref: float,
    method: str = "mean",
) -> float:
    """Calculate the hazard value for flood hazard.

    Parameters
    ----------
    hazard : list
        Raw hazard values.
    ref : float
        Reference to the hazard values.
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
    hazard = AREA_METHODS[method](hazard) - ref
    return hazard, redf


def fn_impact(
    hazard: float | int,
    exposure: float | int,
    fact: float | int,
    fn_curve: Callable,
) -> float:
    """_summary_.

    Parameters
    ----------
    hazard : float | int
        _description_
    exposure : float | int
        _description_
    fact : float | int
        _description_
    fn_curve : Callable
        _description_

    Returns
    -------
    float
        _description_
    """
    f = fn_curve(hazard)
    val = f * exposure * fact
    return val
