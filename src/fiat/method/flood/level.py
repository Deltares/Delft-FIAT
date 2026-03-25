"""Flood level impact functions."""

import math

from fiat.method.flood.depth import fn_impact
from fiat.method.util import ZONAL_METHODS
from fiat.util import FLOOD_LEVEL, LEVEL

__all__ = ["fn_impact"]

COLUMNS = ["reference", "elevation"]
NAME = FLOOD_LEVEL
NEW_COLUMNS = [LEVEL]
TYPES = [f"water_{LEVEL}"]


def fn_hazard(
    hazard: list[float],
    reference: float,
    elevation: float,
    method: str = "mean",
) -> tuple[float]:
    """Calculate the hazard value for flood level hazard.

    Parameters
    ----------
    hazard : list
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
    # Remove the negative hazard values to 0.
    raw_l = len(hazard)
    hazard = [n for n in hazard if n - reference > 0]
    if not hazard:
        return math.nan, math.nan
    redf = len(hazard) / raw_l
    hazard = ZONAL_METHODS[method](hazard) - elevation
    return hazard, redf
