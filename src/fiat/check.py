"""Checks for the data of FIAT."""

import re
from pathlib import Path

from osgeo import osr

from fiat.error import FIATDataError
from fiat.log import spawn_logger
from fiat.util import deter_type, get_srs_repr

logger = spawn_logger("fiat.checks")


## Config
def check_config_entries(
    keys: tuple,
    mandatory_entries: list | tuple,
):
    """Check the mandatory config entries."""
    _check = [
        any([re.match(item, value) for value in keys]) for item in mandatory_entries
    ]
    if not all(_check):
        _missing = [item for item, b in zip(mandatory_entries, _check) if not b]
        msg = f"Missing mandatory entries in the settings. Please fill in the \
following missing entries: {_missing}"
        raise FIATDataError(msg)


def check_config_grid(
    cfg: object,
):
    """Check the grid config entries."""
    _req_fields = [
        "exposure.grid.file",
    ]
    _all_grid = [item for item in cfg if item.startswith("exposure.grid")]
    if len(_all_grid) == 0:
        return False

    _check = [item in _all_grid for item in _req_fields]
    if not all(_check):
        _missing = [item for item, b in zip(_req_fields, _check) if not b]
        logger.warning(
            f"Info for the grid (raster) model was found, but not all. \
{_missing} was/ were missing"
        )
        return False

    return True


def check_global_crs(
    srs: osr.SpatialReference,
):
    """Check the global spatial reference system.

    This should exist.
    """
    if srs is None:
        msg = "Could not infer the srs from '{}', nor from '{}'"
        raise FIATDataError(msg)


## Text files
def check_duplicate_columns(
    cols,
):
    """Check for duplicate column headers."""
    if cols is not None:
        msg = f"Duplicate columns were encountered. Wrong column could \
be used. Check input for these columns: {cols}"
        raise FIATDataError(msg)


## GIS
def check_grid_exact(
    haz,
    exp,
):
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
):
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
):
    """Check whether the geometries lie within the bounds of the hazard data."""
    _checks = (
        gm_bounds[0] > gr_bounds[0],
        gm_bounds[1] < gr_bounds[1],
        gm_bounds[2] > gr_bounds[2],
        gm_bounds[3] < gr_bounds[3],
    )

    if not all(_checks):
        msg = f"Geometry bounds {gm_bounds} exceed hazard bounds {gr_bounds}"
        logger.warning(msg)


def check_vs_srs(
    global_srs: osr.SpatialReference,
    source_srs: osr.SpatialReference,
):
    """Check if the spatial reference systems match."""
    if not (
        global_srs.IsSame(source_srs)
        or global_srs.ExportToProj4() == source_srs.ExportToProj4()
    ):
        return False

    return True


## Hazard
def check_hazard_band_names(
    bnames: list,
    risk: bool,
    rp: list,
    count: int,
):
    """Check the band names of the hazard data."""
    if risk:
        return [f"{n}y" for n in rp]

    if count == 1:
        return [""]

    return bnames


def check_hazard_rp(
    rp_bands: list,
    rp_cfg: list,
    path: Path,
):
    """Check the return periods of the hazard data.

    Applies to risk calculations.
    """
    l = len(rp_bands)

    bn_str = "\n".join(rp_bands).encode()
    if deter_type(bn_str, l - 1) != 3:
        return [float(n) for n in rp_bands]

    if rp_cfg is not None:
        if len(rp_cfg) == len(rp_bands):
            rp_str = "\n".join([str(n) for n in rp_cfg]).encode()
            if deter_type(rp_str, l - 1) != 3:
                return [float(n) for n in rp_cfg]

    msg = f"'{path.name}': cannot determine the return periods for \
the risk calculation. Return periods specified with the bands are: {rp_bands}, \
return periods in settings toml are: {rp_cfg}"
    raise FIATDataError(msg)


def check_hazard_subsets(
    sub: dict,
    path: Path,
):
    """Check whether there are subsets available."""
    if sub is not None:
        keys = ", ".join(list(sub.keys()))
        msg = f"'{path.name}': cannot read this file as there are \
multiple datasets (subsets). Chose one of the following subsets: {keys}"
        raise FIATDataError(msg)


## Exposure
def check_exp_columns(
    index_col: str,
    columns: tuple | list,
    specific_columns: tuple | list = [],
):
    """Check the columns of the exposure data."""
    _man_columns = [
        index_col,
    ] + specific_columns

    _check = [item in columns for item in _man_columns]
    if not all(_check):
        _missing = [item for item, b in zip(_man_columns, _check) if not b]
        msg = f"Missing mandatory exposure columns: {_missing}"
        raise FIATDataError(msg)


def check_exp_derived_types(
    type: str,
    found: tuple | list,
    missing: tuple | list,
):
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


def check_exp_grid_dmfs(
    exp: object,
    dmfs: tuple | list,
):
    """Check the damage functions mentioned in the exposure bands."""
    _ef = [_i.get_metadata_item("fn_damage") for _i in exp]
    _i = None

    _check = [item in dmfs for item in _ef]
    if not all(_check):
        _missing = [item for item, b in zip(_ef, _check) if not b]
        msg = f"Incorrect damage function identifier found in exposure grid: {_missing}"
        raise FIATDataError(msg)


def check_exp_index_col(
    obj: object,
    index_col: type,
):
    """Check whether the index column exists in the exposure geometry dataset."""
    if index_col not in obj.columns:
        raise FIATDataError(f"Index column ('{index_col}') not found in {obj.path}")


## Vulnerability
