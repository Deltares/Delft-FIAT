"""Checks for the data of FIAT."""

from itertools import chain
from pathlib import Path
from typing import Any

from osgeo import osr
from pyproj.crs import CRS

from fiat.cfg import Configurations
from fiat.error import FIATDataError
from fiat.log import spawn_logger
from fiat.struct import Container
from fiat.util import EXPOSURE_GRID_FILE, deter_type, get_srs_repr

logger = spawn_logger(__name__)


## Config
def check_available_values(
    value: Any,
    available: list[Any],
    msg: str,
) -> None:
    """Check whether this settings is available."""
    if value not in available:
        raise FIATDataError(
            f"{msg} value: '{value}' invalid, chose from {available}",
        )


def check_config_entries(
    cfg: Configurations,
    mandatory_entries: list | tuple,
) -> None:
    """Check the mandatory config entries."""
    _check = [cfg.get(item) for item in mandatory_entries]
    if not all(_check):
        _missing = [item for item, b in zip(mandatory_entries, _check) if not b]
        msg = f"Missing mandatory entries in the settings. Please fill in the \
following missing entries: {_missing}"
        raise FIATDataError(msg)


def check_config_grid(
    cfg: Configurations,
) -> bool:
    """Check the grid config entries."""
    entry = cfg.get(EXPOSURE_GRID_FILE)
    if entry is None:
        logger.warning(
            f"Info for the grid (raster) model was found, but not all. \
            {EXPOSURE_GRID_FILE} was/ were missing"
        )
        return False

    return True


## Text files
def check_duplicate_columns(
    cols: tuple | list,
) -> None:
    """Check for duplicate column headers."""
    if cols is not None:
        msg = f"Duplicate columns were encountered. Wrong column could \
be used. Check input for these columns: {cols}"
        raise FIATDataError(msg)


## GIS
def check_grid_exact(
    haz,
    exp,
) -> bool:
    """Check whether the hazard and exposure grid align."""
    if not check_vs_srs(
        haz.srs,
        exp.srs,
    ):
        msg = f"CRS of hazard data ({get_srs_repr(haz.srs)}) does not match the \
CRS of the exposure data ({get_srs_repr(exp.srs)})"
        logger.warning(msg)
        return False

    gtf1 = [round(_n, 2) for _n in haz.geotransform]
    gtf2 = [round(_n, 2) for _n in exp.geotransform]

    if gtf1 != gtf2:
        msg = f"Geotransform of hazard data ({gtf1}) does not match geotransform of \
exposure data ({gtf2})"
        logger.warning(msg)
        return False

    if haz.shape != exp.shape:
        msg = f"Shape of hazard ({haz.shape}) does not match shape of \
exposure data ({exp.shape})"
        logger.warning(msg)
        return False

    return True


def check_internal_srs(
    source_srs: osr.SpatialReference,
    fname: str,
) -> None:
    """Check the internal spatial reference system.

    This also should exist.
    """
    if source_srs is None:
        msg = f"Coordinate reference system is unknown for '{fname}', \
cannot safely continue"
        raise FIATDataError(msg)


def check_geom_extent(
    gm_bounds: tuple | list,
    gr_bounds: tuple | list,
) -> None:
    """Check whether the geometries lie within the bounds of the hazard data."""
    _checks = (
        gm_bounds[0] >= gr_bounds[0],
        gm_bounds[1] >= gr_bounds[1],
        gm_bounds[2] <= gr_bounds[2],
        gm_bounds[3] <= gr_bounds[3],
    )

    if not all(_checks):
        msg = f"Geometry bounds {gm_bounds} exceed hazard bounds {gr_bounds}"
        logger.warning(msg)


def check_vs_srs(
    global_srs: osr.SpatialReference,
    source_srs: osr.SpatialReference,
):
    """Check if the spatial reference systems match."""
    return CRS.from_user_input(global_srs.ExportToWkt()) == CRS.from_user_input(
        source_srs.ExportToWkt()
    )


## Input Data
def check_input_data(
    *input: list[str, Any, type],
) -> None:
    """Check if all input data is present."""
    for item in input:
        name, data, dtype = item
        if isinstance(data, Container):
            if len(data) == 0:
                raise ValueError(f"{name} is empty")
            if not all(isinstance(e, dtype) for e in data):
                raise TypeError(f"Wrong type encountered in {name}")
            continue
        if data is None or not isinstance(data, dtype):
            raise TypeError(
                f"{name} is incorrectly set, \
currently of type {data.__class__.__name__}"
            )


## Hazard
def check_hazard_identifier(
    ids: list[str],
    indices_type: list[list[int]],
) -> tuple[list[int]]:
    """Check the identifiers in the hazard data."""
    # Length per
    l = len(indices_type[0])

    ids_list = []
    # Per type check the validity
    for idxs in indices_type:
        single_type = [ids[i] for i in idxs]
        if len(set(single_type)) != l:
            raise FIATDataError(f"Identifiers set incorrectly for type: {single_type}")
        ids_list.append(single_type)

    # Do a check on the total rp
    ids = list(set(chain(*ids_list)))  # What a beauty
    if len(ids) != l:
        raise FIATDataError(f"Identifiers across types do not match total: {ids}")

    return ids_list[0], ids_list


def check_hazard_rp(
    rp: list,
) -> list[float]:
    """Check the typing of the return periods.

    Applies to risk calculations.
    """
    bn_str = "\n".join(rp).encode()
    if deter_type(bn_str, len(rp) - 1) == 3:
        raise FIATDataError(f"Wrong type in return periods: {rp}")
    return [float(n) for n in rp]


def check_hazard_subsets(
    sub: dict,
    path: Path,
) -> None:
    """Check whether there are subsets available."""
    if sub is not None:
        keys = ", ".join(list(sub.keys()))
        msg = f"'{path.name}': cannot read this file as there are \
multiple datasets (subsets). Chose one of the following subsets: {keys}"
        raise FIATDataError(msg)


def check_hazard_types(
    types: list,
    mandatory_types: list,
) -> list[int]:
    """Check the hazard types in the dataset."""
    check = [item in types for item in mandatory_types]
    if not all(check):
        missing = [item for item, b in zip(mandatory_types, check) if not b]
        msg = f"Missing mandatory hazard types: {missing}"
        raise FIATDataError(msg)

    # Check the count per type
    count = [types.count(item) for item in mandatory_types]
    if len(set(count)) != 1:
        raise FIATDataError(
            f"Different number of datasets per type: {mandatory_types} -> {count}"
        )

    # Set the indices
    indices = [
        [idx for idx, entry in enumerate(types) if entry == item]
        for item in mandatory_types
    ]
    return indices


## Exposure
def check_exp_columns(
    columns: tuple | list,
    mandatory_columns: tuple | list = [],
) -> None:
    """Check the columns of the exposure data."""
    check = [item in columns for item in mandatory_columns]
    if not all(check):
        missing = [item for item, b in zip(mandatory_columns, check) if not b]
        msg = f"Missing mandatory exposure columns: {missing}"
        raise FIATDataError(msg)


def check_exp_derived_types(
    type: str,
    found: tuple | list,
    missing: tuple | list,
) -> None:
    """Check whether columns are available for a certain exposure type."""
    # Error when no columns are found for vulnerability type
    if not found:
        msg = f"For type: '{type}' no matching columns were found for \
fn_{type}_* and max_{type}_* columns."
        raise FIATDataError(msg)

    # Log when combination of fn and max is missing
    if missing:
        logger.warning(
            f"No every damage function has a corresponding \
maximum potential damage: {missing}"
        )


def check_exp_grid_fn(
    fn_list: tuple | list,
    fn_available: tuple | list,
) -> None:
    """Check the impact functions mentioned in the exposure bands."""
    _check = [item in fn_available for item in fn_list]
    if not all(_check):
        _missing = [item for item, b in zip(fn_list, _check) if not b]
        msg = f"Unknown impact function identifier found in exposure grid: {_missing}"
        raise FIATDataError(msg)


## Vulnerability
