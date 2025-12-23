"""Functions specifically for flood risk calculation."""

import math

from numpy import isnan
from osgeo import ogr

from fiat.method.util import AREA_METHODS
from fiat.struct import Table

MANDATORY_COLUMNS = ["ref"]
NEW_COLUMNS = ["depth"]


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
    hazard = [n - ref for n in hazard if (n - ref) > 0.0001]

    if not hazard:
        return math.nan, math.nan

    redf = 1

    if method.lower() == "mean":
        redf = len(hazard) / raw_l

    if len(hazard) > 1:
        hazard = AREA_METHODS[method.lower()](hazard)
    else:
        hazard = hazard[0]

    return hazard, redf


def fn_impact(
    ft: ogr.Feature | list,
    hazard: float | int,
    fact: float | int,
    indices_type: dict,
    vulnerability: Table,
    minv: float | int,
    maxv: float | int,
    sigdec: int,
) -> tuple:
    """Calculate the damage corresponding with the hazard value.

    Parameters
    ----------
    ft : ogr.Feature | list
        A feature or feature info (whichever has to contain the exposure data).
        See docs on running FIAT with an without csv.
    hazard : float | int
        The representative hazard value.
    fact : float | int
        The reduction factor. How much to compensate for the lack of touching the grid
        by an object (geometry).
    indices_type : dict
        The exposure types and corresponding column id's.
    vulnerability : Table
        Vulnerability data.
    minv : float | int
        Minimum value of the index of the vulnerability data.
    maxv : float | int
        Maximum value of the index of the vulnerability data.
    sigdec : int
        Significant decimals to be used.

    Returns
    -------
    tuple
        Damage values.
    """
    # unpack type_dict
    fn = indices_type["fn"]
    exposure = indices_type["max"]

    # Define outgoing list of values
    out = [0] * (len(fn) + 1)

    # Calculate the damage per catagory, and in total (_td)
    total = 0
    idx = 0
    for key, col in fn.items():
        if isnan(hazard) or ft[col] is None or ft[col] == "nan":
            val = "nan"
        else:
            hazard = max(min(maxv, hazard), minv)
            f = vulnerability[round(hazard, sigdec), ft[col]]
            val = f * ft[exposure[key]] * fact
            val = round(val, 2)
            total += val
        out[idx] = val
        idx += 1

    out[-1] = round(total, 2)

    return out


def fn_impact_single(
    hazard: float | int,
    exposure: float | int,
    fact: float | int,
    vulnerability: Table,
    fn: str,
    sigdec: int,
) -> int | str:
    """Calculate the impact corresponding with the hazard value.

    Parameters
    ----------
    hazard : float | int
        The representative hazard value.
    fact : float | int
        The reduction factor. How much to compensate for the lack of touching the grid
        by an object (geometry).
    vulnerability : Table
        Vulnerability data.
    minv : float | int
        Minimum value of the index of the vulnerability data.
    maxv : float | int
        Maximum value of the index of the vulnerability data.
    sigdec : int
        Significant decimals to be used.

    Returns
    -------
    tuple
        Damage values.
    """
    # Calculate the damage per catagory, and in total (_td)
    if isnan(hazard) or fn is None or fn == "nan":
        return math.nan
    f = vulnerability[round(float(hazard), sigdec), fn]
    val = f * exposure * fact
    return round(val, 2)
