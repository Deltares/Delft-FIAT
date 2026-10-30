"""Geometry model utility."""

import copy
import re
from itertools import product
from pathlib import Path
from typing import Any

from fiat.driver.fgb import CT_FLOAT
from fiat.driver.vector import VectorProfile
from fiat.gis import overlay
from fiat.util import AREA, CENTROID, FN, MAX, TOTAL, re_filter

AREA_METHODS = {
    AREA: overlay.area_mask,
    CENTROID: overlay.centroid_mask,
}


def discover_exp_columns(
    columns: dict,
    type: str,
) -> tuple:
    """Figure out the which are the exposure related columns.

    Parameters
    ----------
    columns : dict
        The columns.
    type : str
        Type of exposure, e.g. damage or affected

    Returns
    -------
    tuple
        Exposure suffix (e.g. structure for damage), index of the columns, \
missing values.
    """
    dmg_idx = []

    # Get column values
    column_vals = list(columns.keys())

    # Patterns
    fn_pat = rf"^{FN}_{type}(_\w+)?$"
    max_pat = rf"^{MAX}_{type}(_\w+)?$"

    # Filter the current columns
    dmg = re_filter(column_vals, fn_pat)
    dmg_suffix = [re.findall(fn_pat, item)[0] for item in dmg]
    mpd = re_filter(column_vals, max_pat)
    mpd_suffix = [re.findall(max_pat, item)[0] for item in mpd]

    # Check the overlap
    _check = [item in mpd_suffix for item in dmg_suffix]

    # Determine the missing values
    missing = [item for item, b in zip(dmg_suffix, _check) if not b]
    for item in missing:
        dmg_suffix.remove(item)

    for val in dmg_suffix:
        dmg_idx.append([columns[f"{FN}_{type}{val}"], columns[f"{MAX}_{type}{val}"]])

    return dmg_suffix, dmg_idx, missing


def generate_output_columns(
    columns: list,
    exposure_types: dict,
    hazard_ids: tuple | list,
    extra: tuple | list = [],
) -> list[str]:
    """Generate the output columns."""
    columns = copy.deepcopy(columns)

    # Loop over the exposure types
    for key, value in exposure_types.items():
        columns += [f"{key}{item}" for item in value]
        columns += [f"{TOTAL}_{key}"]

    # Generate all the output columns
    out = []
    for name in hazard_ids:
        add = [f"{item}_{name}" for item in columns]
        out += add
    out += [f"{x}_{y}" for x, y in product(extra, exposure_types.keys())]

    # Return the output meta
    return out


def set_finalizing_params(
    params: dict[str, Any],
    output_path: Path | str,
    profile: VectorProfile,
    exposure_meta: Any,
):
    """Set the parameters used to finalize a vector file."""
    params[Path(output_path).as_posix()] = {
        "name": Path(output_path).stem,
        "geom_type": profile.geom_type,
        "col_names": list(profile.fields) + list(exposure_meta.new),
        "col_types": list(profile.dtypes) + [CT_FLOAT] * len(exposure_meta.new),
        "crs_wkt": profile.crs_wkt,
        "crs_org": profile.crs_org,
        "crs_code": profile.crs_code,
    }
