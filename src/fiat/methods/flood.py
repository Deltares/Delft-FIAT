"""Functions specifically for flood risk calculation."""

import math

from numpy import isnan
from osgeo import ogr

from fiat.methods.util import AREA_METHODS
from fiat.struct import Table

MANDATORY_COLUMNS = ["ref"]
MANDATORY_ENTRIES = []
NEW_COLUMNS = ["depth"]


def calculate_hazard(
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


def calculate_damage(
    hazard_value: float | int,
    red_fact: float | int,
    ft: ogr.Feature | list,
    type_dict: dict,
    vuln: Table,
    vul_min: float | int,
    vul_max: float | int,
    vul_round: int,
) -> tuple:
    """Calculate the damage corresponding with the hazard value.

    Parameters
    ----------
    hazard_value : float | int
        The representative hazard value.
    red_fact : float | int
        The reduction factor. How much to compensate for the lack of touching the grid
        by an object (geometry).
    ft : ogr.Feature | list
        A feature or feature info (whichever has to contain the exposure data).
        See docs on running FIAT with an without csv.
    type_dict : dict
        The exposure types and corresponding column id's.
    vuln : Table
        Vulnerability data.
    vul_min : float | int
        Minimum value of the index of the vulnerability data.
    vul_max : float | int
        Maximum value of the index of the vulnerability data.
    vul_round : int
        Significant decimals to be used.

    Returns
    -------
    tuple
        Damage values.
    """
    # unpack type_dict
    fn = type_dict["fn"]
    maxv = type_dict["max"]

    # Define outgoing list of values
    out = [0] * (len(fn) + 1)

    # Calculate the damage per catagory, and in total (_td)
    total = 0
    idx = 0
    for key, col in fn.items():
        if isnan(hazard_value) or ft[col] is None or ft[col] == "nan":
            val = "nan"
        else:
            hazard_value = max(min(vul_max, hazard_value), vul_min)
            f = vuln[round(hazard_value, vul_round), ft[col]]
            val = f * ft[maxv[key]] * red_fact
            val = round(val, 2)
            total += val
        out[idx] = val
        idx += 1

    out[-1] = round(total, 2)

    return out


def calculate_damage_single(
    hazard_value: float | int,
    red_fact: float | int,
    fn: str,
    maxv: int | float,
    vuln: Table,
    vul_min: float | int,
    vul_max: float | int,
    vul_round: int,
) -> tuple:
    """Calculate the damage corresponding with the hazard value.

    Parameters
    ----------
    hazard_value : float | int
        The representative hazard value.
    red_fact : float | int
        The reduction factor. How much to compensate for the lack of touching the grid
        by an object (geometry).
    ft : ogr.Feature | list
        A feature or feature info (whichever has to contain the exposure data).
        See docs on running FIAT with an without csv.
    type_dict : dict
        The exposure types and corresponding column id's.
    vuln : Table
        Vulnerability data.
    vul_min : float | int
        Minimum value of the index of the vulnerability data.
    vul_max : float | int
        Maximum value of the index of the vulnerability data.
    vul_round : int
        Significant decimals to be used.

    Returns
    -------
    tuple
        Damage values.
    """
    # Calculate the damage per catagory, and in total (_td)
    if isnan(hazard_value) or fn is None or fn == "nan":
        return "nan"
    hazard_value = max(min(vul_max, hazard_value), vul_min)
    f = vuln[round(hazard_value, vul_round), fn]
    val = f * maxv * red_fact
    return round(val, 2)
