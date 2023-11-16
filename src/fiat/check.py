"""Checks for the data of FIAT."""

import fnmatch
import sys
from pathlib import Path

from osgeo import osr

from fiat.log import setup_default_log, spawn_logger
from fiat.util import deter_type

logger = spawn_logger("fiat.checks")


## Config
def check_config_entries(
    keys: tuple,
    path: Path,
    parent: Path,
):
    """_summary_."""
    _man_cols = [
        "output.path",
        "hazard.file",
        "hazard.risk",
        "hazard.elevation_reference",
        "vulnerability.file",
    ]

    _check = [item in keys for item in _man_cols]
    if not all(_check):
        error_log = setup_default_log(
            "error",
            level=2,
            dst=str(parent),
        )
        _missing = [item for item, b in zip(_man_cols, _check) if not b]
        error_log.error(f"Missing mandatory entries in '{path.name}'")
        error_log.info(f"Please fill in the following missing entries: {_missing}")
        sys.exit()


def check_config_geom(
    cfg: object,
):
    """_summary_."""
    _req_fields = [
        "exposure.csv.file",
        "exposure.geom.crs",
        "exposure.geom.file1",
    ]
    _all_geom = [
        item for item in cfg if item.startswith(("exposure.geom", "exposure.csv"))
    ]
    if len(_all_geom) == 0:
        return False

    _check = [item in _all_geom for item in _req_fields]
    if not all(_check):
        _missing = [item for item, b in zip(_req_fields, _check) if not b]
        logger.warning(
            f"Info for the geometry model was found, but not all. \
{_missing} was/ were missing"
        )
        return False

    return True


def check_config_grid(
    cfg: object,
):
    """_summary_."""
    _req_fields = [
        "exposure.grid.crs",
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
    fname: str,
    fname_haz: str,
):
    """_summary_."""
    if srs is None:
        logger.error("Could not infer the srs from '{}', nor from '{}'")
        logger.dead("Exiting...")
        sys.exit()


## Text files
def check_duplicate_columns(
    cols,
):
    """_summary_."""
    if cols is not None:
        logger.error(
            f"Duplicate columns were encountered. Wrong column could \
be used. Check input for these columns: {cols}"
        )
        sys.exit()


## GIS
def check_grid_exact(
    haz,
    exp,
):
    """_summary_."""
    if not check_vs_srs(
        haz.get_srs(),
        exp.get_srs(),
    ):
        logger.error("")
        sys.exit()

    gtf1 = [round(_n, 2) for _n in haz.get_geotransform()]
    gtf2 = [round(_n, 2) for _n in exp.get_geotransform()]

    if gtf1 != gtf2:
        logger.error("")
        sys.exit()

    if haz.shape != exp.shape:
        logger.error("")
        sys.exit()


def check_internal_srs(
    source_srs: osr.SpatialReference,
    fname: str,
    cfg_srs: osr.SpatialReference = None,
):
    """_summary_."""
    if source_srs is None and cfg_srs is None:
        logger.error(
            f"Coordinate reference system is unknown for '{fname}', \
cannot safely continue"
        )
        logger.dead("Exiting...")
        sys.exit()

    if source_srs is None:
        source_srs = osr.SpatialReference()
        source_srs.SetFromUserInput(cfg_srs)
        return source_srs

    return None


def check_geom_extent(
    gm_bounds: tuple | list,
    gr_bounds: tuple | list,
):
    """_summary_."""
    _checks = (
        gm_bounds[0] > gr_bounds[0],
        gm_bounds[1] < gr_bounds[1],
        gm_bounds[2] > gr_bounds[2],
        gm_bounds[3] < gr_bounds[3],
    )

    if not all(_checks):
        logger.error(f"Geometry bounds {gm_bounds} exceed hazard bounds {gr_bounds}")
        sys.exit()


def check_vs_srs(
    global_srs: osr.SpatialReference,
    source_srs: osr.SpatialReference,
):
    """_summary_."""
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
    """_summary_."""
    if risk:
        return [f"{n}Y" for n in rp]

    if count == 1:
        return [""]

    return bnames


def check_hazard_rp_iden(
    bnames: list,
    rp_cfg: list,
    path: Path,
):
    """_summary_."""
    l = len(bnames)

    bn_str = "\n".join(bnames).encode()
    if deter_type(bn_str, l - 1) != 3:
        return [float(n) for n in bnames]

    if rp_cfg is not None:
        if len(rp_cfg) == len(bnames):
            rp_str = "\n".join([str(n) for n in rp_cfg]).encode()
            if deter_type(rp_str, l - 1) != 3:
                return rp_cfg

    logger.error(
        f"'{path.name}': cannot determine the return periods for the risk calculation"
    )
    logger.error(
        f"Names of the bands are: {bnames}, \
return periods in settings toml are: {rp_cfg}"
    )
    logger.info("Specify either one them correctly")
    sys.exit()


def check_hazard_subsets(
    sub: dict,
    path: Path,
):
    """_summary_."""
    if sub is not None:
        keys = ", ".join(list(sub.keys()))
        logger.error(
            f"""'{path.name}': cannot read this file as there are \
multiple datasets (subsets)"""
        )
        logger.info(f"Chose one of the following subsets: {keys}")
        sys.exit()


## Exposure
def check_exp_columns(
    columns: tuple | list,
):
    """_summary_."""
    _man_columns = [
        "Object ID",
        "Ground Elevation",
        "Ground Floor Height",
    ]

    _check = [item in columns for item in _man_columns]
    if not all(_check):
        _missing = [item for item, b in zip(_man_columns, _check) if not b]
        logger.error(f"Missing mandatory exposure columns: {_missing}")
        sys.exit()

    dmg = fnmatch.filter(columns, "Damage Function: *")
    dmg_suffix = [item.split(":")[1].strip() for item in dmg]
    mpd = fnmatch.filter(columns, "Max Potential Damage: *")
    mpd_suffix = [item.split(":")[1].strip() for item in mpd]

    if not dmg:
        logger.error("No damage function were given in ")
        sys.exit()

    if not mpd:
        logger.error("No maximum potential damages were given in ")
        sys.exit()

    _check = [item in mpd_suffix for item in dmg_suffix]
    if not any(_check):
        logger.error(
            "Damage function and maximum potential damage do not have a single match"
        )
        sys.exit()
    if not all(_check):
        _missing = [item for item, b in zip(dmg_suffix, _check) if not b]
        logger.warning(
            f"No every damage function has a corresponding \
maximum potential damage: {_missing}"
        )


def check_exp_grid_dmfs(
    exp: object,
    dmfs: tuple | list,
):
    """_summary_."""
    _ef = [_i.get_metadata_item("damage_function") for _i in exp]
    _i = None

    _check = [item in dmfs for item in _ef]
    if not all(_check):
        _missing = [item for item, b in zip(_ef, _check) if not b]
        logger.error(
            f"Incorrect damage function identifier found in exposure grid: {_missing}",
        )
        sys.exit()


## Vulnerability
