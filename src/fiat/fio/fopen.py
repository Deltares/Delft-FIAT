"""Open datasets."""

from pathlib import Path

from fiat.fio.geom import GeomIO
from fiat.fio.grid import GridSource
from fiat.fio.handler import BufferHandler
from fiat.fio.parser import CSVParser
from fiat.struct import Table, TableLazy

__all__ = ["open_csv", "open_geom", "open_grid"]


## Open
def open_csv(
    file: Path | str,
    delimiter: str = ",",
    header: bool = True,
    index: str = None,
    lazy: bool = False,
) -> object:
    """Open a csv file.

    Parameters
    ----------
    file : str
        Path to the file.
    delimiter : str, optional
        Column seperating character, either something like `','` or `';'`.
    header : bool, optional
        Whether or not to use headers.
    index : str, optional
        Name of the index column.
    lazy : bool, optional
        If `True`, a lazy read is executed.

    Returns
    -------
    Table | TableLazy
        Object holding parsed csv data.
    """
    handler = BufferHandler(file)

    parser = CSVParser(
        handler,
        delimiter,
        header,
        index,
    )

    if lazy:
        return TableLazy(
            data=parser.data,
            index=parser.index,
            columns=parser.columns,
            **parser.meta,
        )

    return Table.from_parser(
        parser=parser,
    )


def open_geom(
    file: Path | str,
    mode: str = "r",
    overwrite: bool = False,
    srs: str | None = None,
) -> GeomIO:
    """Open a geometry source file.

    This source file is lazily read.

    Parameters
    ----------
    file : str
        Path to the file.
    mode : str, optional
        Open in `read` or `write` mode.
    overwrite : bool, optional
        Whether or not to overwrite an existing dataset.
    srs : str, optional
        A Spatial reference system string in case the dataset has none.

    Returns
    -------
    GeomIO
        Object that holds a connection to the source file.
    """
    return GeomIO(
        file,
        mode,
        overwrite,
        srs,
    )


def open_grid(
    file: Path | str,
    mode: str = "r",
    srs: str | None = None,
    chunk: tuple = None,
    subset: str = None,
    var_as_band: bool = False,
):
    """Open a grid source file.

    This source file is lazily read.

    Parameters
    ----------
    file : Path | str
        Path to the file.
    mode : str, optional
        Open in `read` or `write` mode.
    srs : str, optional
        A Spatial reference system string in case the dataset has none.
    chunk : tuple, optional
        Chunk size in x and y direction.
    subset : str, optional
        In netCDF files, multiple variables are seen as subsets and can therefore not
        be loaded like normal bands. Specify one if one of those it wanted.
    var_as_band : bool, optional
        Again with netCDF files: if all variables have the same dimensions, set this
        flag to `True` to look the subsets as bands.

    Returns
    -------
    GridSource
        Object that holds a connection to the source file.
    """
    return GridSource(
        file,
        mode,
        srs,
        chunk,
        subset,
        var_as_band,
    )
