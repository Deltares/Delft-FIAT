"""Flood level impact functions."""

import math

import numpy as np

from fiat._core import zonal_reduce
from fiat.method.flood.depth import fn_impact
from fiat.method.util import ZONAL_CODES
from fiat.util import DEPTH, FLOOD_LEVEL, LEVEL

__all__ = ["fn_impact"]

COLUMNS = ["reference", "elevation"]
NAME = FLOOD_LEVEL
NEW_COLUMNS = [DEPTH]
TYPES = [f"water_{LEVEL}"]


def fn_hazard(
    hazard: np.ndarray | list[float],
    reference: float,
    elevation: float,
    method: str = "mean",
) -> tuple[float]:
    """Calculate the hazard value for flood level hazard.

    Parameters
    ----------
    hazard : np.ndarray | list
        Raw hazard values.
    reference : float
        Surface elevation reference to the hazard values.
    elevation : float
        The elevation of the object relative to the surface.
    method : str, optional
        Chose 'max' or 'mean' for either the maximum value or the average,
        by default 'mean'.

    Returns
    -------
    float
        A representative hazard value.
    """
    # Subtract the reference, filter to positive values and reduce in one pass.
    value, redf = zonal_reduce(
        np.ascontiguousarray(hazard, dtype=np.float64),
        ZONAL_CODES[method],
        reference,
    )
    if math.isnan(value):
        return math.nan, math.nan
    return value - elevation, redf
