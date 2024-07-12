"""Functions specifically for flood risk calculation."""
import math

from numpy import isnan, ndarray

from fiat.io import Table
from fiat.math.util import AREA_METHODS

MANDATORY_COLUMNS = ["ground_elevtn", "ground_flht"]
MANDATORY_ENTRIES = {"ref": "hazard.elevation_reference"}
NEW_COLUMNS = ["inun_depth"]


def calculate_hazard(
    haz: list,
    ref: str,
    gfh: float,
    ge: float = 0,
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
    if ref.lower() == "datum" and not math.isnan(ge):
        # The hazard data is referenced to a Datum
        # (e.g., for flooding this is the water elevation).
        _ge = ge

    # Remove the negative hazard values to 0.
    raw_l = len(haz)
    haz = [n - _ge for n in haz if (n - _ge) > 0.0001]

    if not haz:
        return math.nan, math.nan

    redf = 1

    if method.lower() == "mean":
        redf = len(haz) / raw_l

    if len(haz) > 1:
        haz = AREA_METHODS[method.lower()](haz)
    else:
        haz = haz[0]

    # Subtract the Ground Floor Height from the hazard value
    haz = haz - gfh

    return haz, redf


def calculate_wcsv(
    hazard_values: ndarray,
    info: tuple | list,
    fn: dict,
    max_val: dict,
    vuln: Table,
    vul_min: float | int,
    vul_max: float | int,
    vul_round: int,
    reference: str = "dem",
    ground_elevtn: float | int = 0,
    ground_flht: float | int = 0,
):
    """Calculate damage as a result of flooding."""
    # Define outgoing list of values
    out = [0] * (len(fn) + 3)

    # Calculate the inundation
    inun, redf = calculate_hazard(
        hazard_values.tolist(),
        reference,
        ground_flht,
        ground_elevtn,
    )
    out[:2] = (round(inun, 2), round(redf, 2))

    # Calculate the damage per catagory, and in total (_td)
    total = 0
    idx = 0
    for key, col in fn.items():
        if isnan(inun) or str(info[col]) == "nan":
            val = "nan"
        else:
            inun = max(min(vul_max, inun), vul_min)
            f = vuln[round(inun, vul_round), info[col]]
            val = f * info[max_val[key]] * redf
            val = round(val, 2)
            total += val
        out[2 + idx] = val
        idx += 1

    out[-1] = round(total, 2)

    return out
