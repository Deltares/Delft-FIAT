"""The FIAT model workers."""

from pathlib import Path

from osgeo import ogr

from fiat.util import NEWLINE_CHAR

GEOM_DEFAULT_CHUNK = 50000
GRID_PREFER = {
    False: "hazard",
    True: "exposure",
}


def get_field_values(
    ft: ogr.Feature,
    mid: int,
    idxs_haz: list | tuple,
) -> tuple:
    """Get exposure info from feature."""
    method = ft.GetField(mid)
    haz = [ft.GetField(idx) for idx in idxs_haz]
    return method, haz


def csv_def_file(
    p: Path | str,
    columns: tuple | list,
) -> None:
    """Set up the outgoing csv file.

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


def get_file_entries(
    files: list[dict] | None,
    paths: list[Path | str] | None,
) -> tuple:
    """Get multiple file entries from the configurations."""
    if paths is None:
        paths = [item.get("file", None) for item in files]
    else:
        files = [{} for _ in paths]
    return files, paths
