"""Geometry model utility."""

from fiat.check import check_exp_columns, check_exp_derived_types
from fiat.struct.container import ExposureGeomMeta
from fiat.typing import MethodsProtocol
from fiat.util import discover_exp_columns, generate_output_columns


def get_exposure_meta(
    columns: dict,
    module: MethodsProtocol,
    types: list | tuple,
    bands: list | tuple,
    risk: bool,
):
    """Simple method for sorting out the exposure meta."""  # noqa: D401
    mandatory_columns = getattr(module, "MANDATORY_COLUMNS")
    # Check the exposure column headers
    check_exp_columns(
        list(columns.keys()),
        mandatory_columns=mandatory_columns,
    )
    indices_spec = [columns[item] for item in mandatory_columns]

    # Check the found columns
    types_dict = {}
    for t in types:
        types_dict[t] = {}
        found, found_idx, missing = discover_exp_columns(columns, type=t)
        check_exp_derived_types(t, found, missing)
        types_dict[t] = found_idx

    ## Information for output
    extra = []
    if risk:
        extra = ["ead"]
    new, type_length, indices_total = generate_output_columns(
        getattr(module, "NEW_COLUMNS"),
        types_dict,
        extra=extra,
        suffix=bands,
    )

    # Set the indices for the outgoing columns
    indices_new = list(range(len(columns), len(columns) + len(new)))

    meta = ExposureGeomMeta(
        indices_new=indices_new,
        indices_spec=indices_spec,
        indices_total=indices_total,
        indices_type=types_dict,
        new=new,
        type_length=type_length,
    )
    return meta
