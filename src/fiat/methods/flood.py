"""Functions specifically for flood risk calculation."""
import math

from numpy import isnan

from fiat.io import Table
from fiat.methods.util import AREA_METHODS

MANDATORY_COLUMNS = ["ground_elevtn", "ground_flht"]
MANDATORY_ENTRIES = {"ref": "hazard.elevation_reference"}
NEW_COLUMNS = ["inun_depth"]


def calculate_hazard(
    hazard: list,
    reference: str,
    ground_flht: float,
    ground_elevtn: float = 0,
    method: str = "mean",
) -> float:
    """_summary_.

    Parameters
    ----------
    haz : list
        _description_
    ref : str
        _description_
    gfh : float
        _description_
    ge : float, optional
        Ground Elevation, by default 0
    method : str, optional
        _description_, by default "mean"

    Returns
    -------
    float
        _description_
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
    info: tuple | list,
    type_dict: dict,
    vuln: Table,
    vul_min: float | int,
    vul_max: float | int,
    vul_round: int,
):
    """Calculate damage as a result of flooding."""
    # unpack type_dict
    fn = type_dict["fn"]
    maxv = type_dict["max"]

    # Define outgoing list of values
    out = [0] * (len(fn) + 1)

    # Calculate the damage per catagory, and in total (_td)
    total = 0
    idx = 0
    for key, col in fn.items():
        if isnan(hazard_value) or str(info[col]) == "nan":
            val = "nan"
        else:
            hazard_value = max(min(vul_max, hazard_value), vul_min)
            f = vuln[round(hazard_value, vul_round), info[col]]
            val = f * info[maxv[key]] * red_fact
            val = round(val, 2)
            total += val
        out[idx] = val
        idx += 1

    out[-1] = round(total, 2)

    return out
