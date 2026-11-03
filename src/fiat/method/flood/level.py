"""Flood level impact functions."""

import math

import numpy as np

from fiat._core import zonal_reduce
from fiat.method.flood.depth import fn_impact
from fiat.method.util import ZONAL_CODES
from fiat.util import DEPTH, FLOOD_LEVEL, LEVEL

__all__ = ["fn_hazard", "fn_impact"]

COLUMNS = ["reference", "elevation"]
NAME = FLOOD_LEVEL
NDATASETS = 1
NEW_COLUMNS = [DEPTH]
TYPES = [f"water_{LEVEL}"]
AXIS_TYPES = [f"water_{DEPTH}"]


def fn_hazard(
    hazards: tuple[np.ndarray, ...],
    reference: float,
    elevation: float,
    method: str = "mean",
) -> tuple[tuple[float, ...], float]:
    """Calculate the hazard value for flood level hazard.

    Parameters
    ----------
    hazards : tuple[np.ndarray, ...]
        Raw hazard values, one array (water level).
    reference : float
        Surface elevation reference to the hazard values.
    elevation : float
        The elevation of the object relative to the surface.
    method : str, optional
        Chose 'max', 'mean' or 'min' for the maximum, average or minimum value,
        by default 'mean'.

    Returns
    -------
    tuple[tuple[float, ...], float]
        The representative hazard value(s) (water depth) and the reduction factor.
    """
    # Subtract the reference, filter to positive values and reduce in one pass.
    value, redf = zonal_reduce(
        np.ascontiguousarray(hazards[0], dtype=np.float64),
        ZONAL_CODES[method],
        reference,
    )
    if math.isnan(value):
        return (math.nan,), math.nan
    return (value - elevation,), redf
