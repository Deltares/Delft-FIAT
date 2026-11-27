"""Casualties functions submodule."""

import math
from typing import Callable

import numpy as np

from fiat._core import zonal_reduce
from fiat.method.util import ZONAL_CODES
from fiat.util import CASUALTIES, DEPTH, RISING, VALUE, VELOCITY, WATER

__all__ = ["fn_hazard", "fn_impact"]

COLUMNS = []
NAME = CASUALTIES
NDATASETS = 2
NEW_COLUMNS = [VALUE]
TYPES = [f"{WATER}_{DEPTH}", VELOCITY, f"{RISING}_{VELOCITY}"]
AXIS_TYPES = [f"{WATER}_{DEPTH}"]


def fn_hazard(
    hazards: tuple[np.ndarray, ...],
    method: str = "mean",
) -> tuple[tuple[float, ...], float]:
    """Calculate the hazard value from a generic hazard.

    Parameters
    ----------
    hazards : tuple[np.ndarray, ...]
        Raw hazard values, one array.
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
    return value, redf


def fn_impact(
    hazards: tuple[float | np.ndarray, ...],
    exposure: float | np.ndarray,
    curves: tuple[Callable[..., float | np.ndarray], ...],
    fact: float,
) -> float | np.ndarray:
    """Calculate the impact from generic hazard data.

    Works on scalars (geometries) as well as on arrays (grid cells).

    Parameters
    ----------
    hazards : tuple[float | np.ndarray, ...]
        The hazard values.
    exposure : float | np.ndarray
        The maximum exposure impact value.
    curves : tuple[Callable, ...]
        The vulnerability curves of zone 2 (high rising speed)
        and zone 4 (low rising speed).
    fact : float
        The reduction factor (area method).

    Returns
    -------
    float | np.ndarray
        Impact.
    """
    # Quickly unpack for readability
    wd, v, rv = hazards
    zn2, zn4 = curves

    # Setup the outgoing array
    out = np.zeros(wd.shape)
    # Move through the zones and populate the outgoing array
    maskz1 = (wd * v >= 7) & (v >= 2)
    return out, maskz1
