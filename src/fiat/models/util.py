"""The FIAT model workers."""

from pathlib import Path

from fiat.util import NEWLINE_CHAR

GEOM_MIN_CHUNK = 50000
GEOM_MIN_WRITE_CHUNK = 20000


def csv_temp_file(
    p: Path | str,
    idx: int,
    index_col: str,
    columns: tuple | list,
):
    """_summary_.

    _extended_summary_
    """
    header = (
        f"{index_col},".encode() + ",".join(columns).encode() + NEWLINE_CHAR.encode()
    )
    with open(Path(p, f"{idx:03d}.dat"), "wb") as _tw:
        _tw.write(header)


def csv_def_file(
    p: Path | str,
    columns: tuple | list,
):
    """_summary_.

    _extended_summary_
    """
    header = b""
    header += ",".join(columns).encode()
    header += NEWLINE_CHAR.encode()

    with open(p, "wb") as _dw:
        _dw.write(header)


def geom_threads(
    cpu_count: int,
    haz_layers: int,
    chunks: int,
):
    """_summary_.

    _extended_summary_
    """
    n = 1
    if chunks == 0:
        chunks = 1
    n = chunks * haz_layers
    n = min(cpu_count, n)

    return n
