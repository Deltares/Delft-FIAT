"""The FIAT model workers."""

from pathlib import Path

from fiat.fio import GridIO
from fiat.util import NEWLINE_CHAR

GEOM_DEFAULT_CHUNK = 50000
GRID_PREFER = {
    False: "hazard",
    True: "exposure",
}


def deter_band_names(
    obj: GridIO,
) -> list:
    """Determine the names of the bands.

    If the bands do not have any names of themselves,
    they will be set to a default.
    """
    names = []
    for n in range(obj.size):
        name = obj.get_band_name(n)
        if not name:
            names.append(f"band{n+1}")
            continue
        names.append(name)

    return names


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
