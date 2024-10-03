"""Functions specifically for flood risk calculation."""
import math

from numpy import isnan
from osgeo import ogr

from fiat.io import Table
from fiat.methods.util import AREA_METHODS

MANDATORY_COLUMNS = ["ground_flht", "ground_elevtn"]
MANDATORY_ENTRIES = {"ref": "hazard.elevation_reference"}
NEW_COLUMNS = ["inun_depth"]


def calculate_hazard(
    hazard: list,
    reference: str,
    ground_flht: float,
    ground_elevtn: float = 0,
    method: str = "mean",
) -> float:
    """Calculate the hazard value for flood hazard.

    Parameters
    ----------
    hazard : list
        Raw hazard values.
    reference : str
        Reference, either 'dem' or 'datum'.
    ground_flht : float
        The height of the floor of an object (.e.g the door elevation).
    ground_elevtn : float, optional
        Ground height in reference to e.g. the ocean.
        (Needed when 'reference' is 'datum')
    method : str, optional
        Chose 'max' or 'mean' for either the maximum value or the average,
        by default 'mean'.

    Returns
    -------
    float
        A representative hazard value.
    """
    _ge = 0
    if reference.lower() == "datum" and not math.isnan(ground_elevtn):
        # The hazard data is referenced to a Datum
        # (e.g., for flooding this is the water elevation).
        _ge = ground_elevtn

    # Remove the negative hazard values to 0.
    raw_l = len(hazard)
    hazard = [n - _ge for n in hazard if (n - _ge) > 0.0001]

    if not hazard:
        return math.nan, math.nan

    redf = 1

    if method.lower() == "mean":
        redf = len(hazard) / raw_l

    if len(hazard) > 1:
        hazard = AREA_METHODS[method.lower()](hazard)
    else:
        hazard = hazard[0]

    # Subtract the Ground Floor Height from the hazard value
    hazard -= ground_flht

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
