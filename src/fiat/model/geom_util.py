"""Geometry model utility."""

import copy
import re
from itertools import product

from fiat.check import check_exp_columns, check_exp_derived_types
from fiat.fio import GeomIO
from fiat.struct.container import ExposureGeomMeta, HazardMeta
from fiat.typing import MethodsProtocol
from fiat.util import re_filter


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
    fn_pat = rf"^fn_{type}(_\w+)?$"
    max_pat = rf"^max_{type}(_\w+)?$"

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
        dmg_idx.append([columns[f"fn_{type}{val}"], columns[f"max_{type}{val}"]])

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
        columns += [f"total_{key}"]

    # Generate all the output columns
    out = []
    for name in hazard_ids:
        add = [f"{item}_{name}" for item in columns]
        out += add
    out += [f"{x}_{y}" for x, y in product(extra, exposure_types.keys())]

    # Return the output meta
    return out


def get_exposure_meta(
    exposure: GeomIO,
    hazard_meta: HazardMeta,
    method: MethodsProtocol,
    types: list | tuple,
):
    """Simple method for sorting out the exposure meta."""  # noqa: D401
    columns = exposure.layer._columns
    mandatory_columns = method.COLUMNS
    # Check the exposure column headers
    check_exp_columns(
        list(columns.keys()),
        mandatory_columns=mandatory_columns,
    )
    indices_spec = [columns[item] for item in mandatory_columns]

    # Check the found columns
    indices_type = {}
    length_type = {}
    type_dict = {}
    for t in types:
        indices_type[t] = {}
        found, found_idx, missing = discover_exp_columns(columns, type=t)
        check_exp_derived_types(t, found, missing)
        indices_type[t] = found_idx
        length_type[t] = len(found)
        type_dict[t] = found

    # The length of columns per hazard
    type_length = (
        hazard_meta.type_length
        + sum([len(item) for item in type_dict.values()])
        + len(type_dict)
    )

    ## Names of the new columns
    extra = []
    if hazard_meta.risk:
        extra = ["ead"]
    new = generate_output_columns(
        method.NEW_COLUMNS,
        type_dict,
        hazard_ids=hazard_meta.ids,
        extra=extra,
    )

    # Indices of colums during calculation
    offset = hazard_meta.type_length
    indices_impact = {}
    indices_total = {}
    for key, value in length_type.items():
        indices_impact[key] = list(
            zip(
                *[
                    range(offset + i, len(new), type_length)[: hazard_meta.length]
                    for i in range(value)
                ]
            )
        )
        indices_total[key] = list(range(offset + value, len(new), type_length))[
            : hazard_meta.length
        ]
        offset += value + 1

    # Set the indices for the outgoing columns
    indices_new = list(range(len(columns), len(columns) + len(new)))

    # Create the exposure meta struct
    meta = ExposureGeomMeta(
        indices_impact=indices_impact,
        indices_new=indices_new,
        indices_spec=indices_spec,
        indices_total=indices_total,
        indices_type=indices_type,
        new=new,
        new_length=len(new),
        type_length=type_length,
    )
    return meta
