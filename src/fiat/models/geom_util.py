"""Geometry model utility."""

from fiat.check import check_exp_columns, check_exp_derived_types
from fiat.struct import FieldMeta
from fiat.typing import MethodsProtocol
from fiat.util import discover_exp_columns, generate_output_columns


def get_exposure_meta(
    columns: dict,
    module: MethodsProtocol,
    exposure_types: list | tuple,
    band_names: list | tuple,
    risk: bool,
):
    """Simple method for sorting out the exposure meta."""  # noqa: D401
    # Check the exposure column headers
    check_exp_columns(
        list(columns.keys()),
        mandatory_columns=getattr(module, "MANDATORY_COLUMNS"),
    )

    # Check the found columns
    types = {}
    for t in exposure_types:
        types[t] = {}
        found, found_idx, missing = discover_exp_columns(columns, type=t)
        check_exp_derived_types(t, found, missing)
        types[t] = found_idx

    ## Information for output
    extra = []
    if risk:
        extra = ["ead"]
    new, length, total = generate_output_columns(
        getattr(module, "NEW_COLUMNS"),
        types,
        extra=extra,
        suffix=band_names,
    )

    # Set the indices for the outgoing columns
    idxs = list(range(len(columns), len(columns) + len(new)))

    return FieldMeta(
        new=new,
        length=length,
        indices=idxs,
        total=total,
        types=types,
    )
