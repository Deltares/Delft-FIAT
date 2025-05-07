"""The FIAT model workers."""

from pathlib import Path

from osgeo import ogr

from fiat.cfg import Configurations
from fiat.fio import TableLazy
from fiat.util import NEWLINE_CHAR, generic_path_check, replace_empty

GEOM_DEFAULT_CHUNK = 50000
GRID_PREFER = {
    False: "hazard",
    True: "exposure",
}


def check_file_for_read(
    cfg: Configurations,
    entry: str,
    path: Path | str,
):
    """Quick check on the input for reading."""
    if path is not None:
        path = generic_path_check(path, cfg.path)
    else:
        path = cfg.get(entry)
    return path


def exposure_from_geom(
    ft: ogr.Feature,
    exp: TableLazy,
    oid: int,
    mid: int,
    idxs_haz: list | tuple,
    pattern: object,
):
    """Get exposure info from feature."""
    method = ft.GetField(mid)
    haz = [ft.GetField(idx) for idx in idxs_haz]
    return ft, [ft.GetField(oid)], method, haz


def exposure_from_csv(
    ft: ogr.Feature,
    exp: TableLazy,
    oid: int,
    mid: int,
    idxs_haz: list | tuple,
    pattern: object,
):
    """Get exposure info from csv file."""
    ft_info_raw = exp[ft.GetField(oid)]
    if ft_info_raw is None:
        return None, None, None, None

    ft_info = replace_empty(pattern.split(ft_info_raw))
    ft_info = [x(y) for x, y in zip(exp.dtypes, ft_info)]
    method = ft_info[exp._columns["extract_method"]].lower()
    haz = [ft_info[idx] for idx in idxs_haz]
    return ft_info, ft_info, method, haz


EXPOSURE_FIELDS = {
    True: exposure_from_geom,
    False: exposure_from_csv,
}


def csv_def_file(
    p: Path | str,
    columns: tuple | list,
):
    """_summary_Set up the outgoing csv file.

    Parameters
    ----------
    p : Path | str
        Path to the file.
    columns : tuple | list
        Headers to be added to the file.
    """
    header = b""
    header += ",".join(columns).encode()
    header += NEWLINE_CHAR.encode()

    with open(p, "wb") as _dw:
        _dw.write(header)
