"""Open datasets."""

from pathlib import Path

from fiat.driver.csv import Table, parse_csv
from fiat.driver.fgb import FlatGeobufReader
from fiat.driver.geotiff import GeotiffReader, GeotiffWriter
from fiat.driver.handler import FileBufferHandler
from fiat.driver.netcdf import NetcdfReader, NetcdfWriter
from fiat.driver.raster import GRID_EXTENSIONS
from fiat.driver.vector import GEOM_EXTENSIONS
from fiat.error import DriverNotFoundError

__all__ = ["open_csv", "open_geom", "open_grid"]

# Map the handles for grid
grid_handles = {
    ".nc": {True: NetcdfWriter, False: NetcdfReader},
    ".tif": {True: GeotiffWriter, False: GeotiffReader},
    ".tiff": {True: GeotiffWriter, False: GeotiffReader},
}


## Open
def open_csv(
    file: Path | str,
    delimiter: str = ",",
    header: bool = True,
    index: str = None,
) -> Table:
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
    handler = FileBufferHandler(file)

    return parse_csv(
        handler,
        delimiter,
        header,
        index,
    )


def open_geom(
    file: Path | str,
    mode: str = "r",
    crs: str | None = None,
) -> FlatGeobufReader:
    """Open a geometry source file.

    This source file is lazily read.

    Parameters
    ----------
    file : str
        Path to the file.
    mode : str, optional
        Open in `read` or `write` mode.
    overwrite : bool, optional
        Whether or not to overwrite an existing dataset (kept for API compatibility).
    crs : str, optional
        A Spatial reference system string in case the dataset has none.

    Returns
    -------
    FlatGeobufReader
        Object that holds a read connection to the source file.
    """
    file = Path(file)
    if file.suffix.lower() not in GEOM_EXTENSIONS:
        raise DriverNotFoundError(gog="Geometry", path=file)

    # Return the handle
    return FlatGeobufReader(file, crs=crs)


def open_grid(
    file: Path | str,
    mode: str = "r",
    crs: str | None = None,
    subset: str = None,
    **kwargs,
) -> NetcdfReader | NetcdfWriter | GeotiffReader | GeotiffWriter:
    """Open a grid source file.

    This source file is lazily read.

    The driver is selected from the file extension: ``.tif`` / ``.tiff`` use the
    hand-rolled GeoTIFF/COG driver, everything else uses the netCDF driver.

    Parameters
    ----------
    file : Path | str
        Path to the file.
    mode : str, optional
        Open in `read` or `write` mode.
    crs : str, optional
        A Spatial reference system string in case the dataset has none..
    subset : str, optional
        In netCDF files, multiple variables are seen as subsets and can therefore not
        be loaded like normal bands. Specify one if one of those it wanted.

    Returns
    -------
    NetcdfReader | NetcdfWriter | GeotiffReader | GeotiffWriter
        Object that holds a connection to the source file. A writer for write mode
        (``w``) and a reader otherwise (``r``, ``a``).
    """
    file = Path(file)
    if file.suffix.lower() not in GRID_EXTENSIONS:
        raise DriverNotFoundError(gog="Grid", path=file)

    # Return a handle
    return grid_handles[file.suffix.lower()][mode == "w"](file, crs, **kwargs)
