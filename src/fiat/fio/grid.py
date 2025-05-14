"""Basic I/O for raster files using GDAL."""

import gc
from pathlib import Path

from osgeo import gdal, osr

from fiat.error import DriverNotFoundError
from fiat.fio.base import BaseIO
from fiat.struct import GridBand
from fiat.util import (
    GRID_DRIVER_MAP,
    get_srs_repr,
    read_gridsource_layers,
)

__all__ = ["GridIO"]


class GridIO(BaseIO):
    """A source object for geospatial gridded data.

    Essentially a gdal Dataset wrapper.

    Parameters
    ----------
    file : str
        The path to a file.
    mode : str, optional
        The I/O mode. Either `r` for reading or `w` for writing.
    srs : str, optional
        A Spatial reference system string in case the dataset has none.
    chunk : tuple, optional
        Chunking size of the data.
    subset : str, optional
        The wanted subset of data. This is applicable to netCDF files containing \
multiple variables.
    var_as_band : bool, optional
        Whether to interpret the variables as bands.
        This is applicable to netCDF files containing multiple variables.

    Examples
    --------
    Can be indexed directly to get a `GridBand` object.
    ```Python
    # Open a file
    gs = open_grid(< path-to-file >)

    # Index it (take the first band)
    grid = gs[1]
    ```
    """

    _type_map = {
        "float": gdal.GFT_Real,
        "int": gdal.GDT_Int16,
        "str": gdal.GFT_String,
    }

    def __new__(
        cls,
        file: str,
        mode: str = "r",
        srs: str | None = None,
        chunk: tuple = None,
        subset: str = None,
        var_as_band: bool = False,
    ):
        """Create a new GridIO object."""
        obj = object.__new__(cls)

        return obj

    def __init__(
        self,
        file: str,
        mode: str = "r",
        srs: str | None = None,
        chunk: tuple = None,
        subset: str = None,
        var_as_band: bool = False,
    ):
        # Supercharge with BaseIO class
        BaseIO.__init__(self, file, mode)

        # Figure out the driver situation
        if self.path.suffix not in GRID_DRIVER_MAP:
            raise DriverNotFoundError(gog="Grid", path=self.path)

        driver = GRID_DRIVER_MAP[self.path.suffix]
        self.driver = gdal.GetDriverByName(driver)

        # Go over the open options, var_as_band really
        open_options = []
        if var_as_band:
            open_options.append("VARIABLES_AS_BANDS=YES")
        self.var_as_band = var_as_band

        # If var_as_band is false, a subset might be requested/ required
        if not subset:
            subset = None
        self.subset = subset
        if subset is not None and not var_as_band:
            self._path = Path(
                f"{driver.upper()}:" + f'"{file}"' + f":{subset}",
            )

        # Some of the internals
        self._bands: list[GridBand] = []
        self._count: int = 0
        self._chunk: tuple = None
        self._dtype: int = None
        self.src: gdal.Dataset = None

        # If write mode, consider initialized
        if self.mode:
            return

        # Otherwise open an existing dataset
        self.src = gdal.OpenEx(self._path.as_posix(), open_options=open_options)
        self._count = self.src.RasterCount

        # Set the chunking
        self._chunk = self.shape
        if chunk is not None:
            self._chunk = chunk

        # Set the bands
        for idx in range(self._count):
            self._bands.append(
                GridBand._create(
                    self.src,
                    band=self.src.GetRasterBand(idx + 1),
                    chunk=self.chunk,
                    mode=self.mode,
                )
            )

        # Set the 'external' srs
        self._srs = None
        if srs is not None:
            self._srs = osr.SpatialReference()
            self._srs.SetFromUserInput(srs)

    def __iter__(self):
        self._cur_index = 1
        return self

    def __next__(self):
        if self._cur_index < self._count + 1:
            r = self[self._cur_index]
            self._cur_index += 1
            return r
        else:
            raise StopIteration

    def __getitem__(
        self,
        oid: int,
    ) -> GridBand:
        return self._bands[oid]

    def __reduce__(self):
        srs = None
        if self._srs is not None:
            srs = get_srs_repr(self._srs)
        return self.__class__, (
            self.path,
            self.mode_str,
            srs,
            self.chunk,
            self.subset,
            self.var_as_band,
        )

    ## Properties
    @property
    def band_names(
        self,
    ) -> list:
        """Get the names of all bands."""
        _names = []
        for n in range(self.size):
            _names.append(self.get_band_name(n + 1))

        return _names

    @property
    @BaseIO.check_state
    def bounds(self) -> tuple:
        """Return the bounds of the GridIO.

        Returns
        -------
        tuple
            Contains the four boundaries of the grid. This take the form of \
[left, right, top, bottom]
        """
        _gtf = self.src.GetGeoTransform()
        return (
            _gtf[0],
            _gtf[0] + _gtf[1] * self.src.RasterXSize,
            _gtf[3] + _gtf[5] * self.src.RasterYSize,
            _gtf[3],
        )

    @property
    def chunk(self) -> tuple:
        """Return the chunking size.

        Returns
        -------
        list
            The chunking in x direction and y direction.
        """
        return self._chunk

    @chunk.setter
    def chunk(
        self,
        value: tuple[int],
    ):
        """Set the chunking size of the grid.

        Parameters
        ----------
        chunk : tuple[int]
            A tuple containing the chunking size in x direction and y direction.
        """
        if len(value) != 2:
            raise ValueError("Chunk should have two elements")
        self._chunk = value
        for item in self:
            item.chunk = self.chunk

    @property
    @BaseIO.check_state
    def dtype(self) -> int:
        """Return the data types of the field data."""
        if not self._dtype:
            _b = self[1]
            self._dtype = _b.dtype
            del _b
        return self._dtype

    @property
    @BaseIO.check_state
    def geotransform(self) -> tuple:
        """Return the geo transform of the grid."""
        return self.src.GetGeoTransform()

    @property
    @BaseIO.check_state
    def shape(self) -> tuple:
        """Return the shape of the grid.

        According to normal reading, i.e. rows, columns.

        Returns
        -------
        tuple
            Contains size in y direction and x direction.
        """
        return (
            self.src.RasterYSize,
            self.src.RasterXSize,
        )

    @property
    @BaseIO.check_state
    def shape_xy(self) -> tuple:
        """Return the shape of the grid.

        According to x-direction first.

        Returns
        -------
        tuple
            Contains size in x direction and y direction.
        """
        return (
            self.src.RasterXSize,
            self.src.RasterYSize,
        )

    @property
    @BaseIO.check_state
    def size(self) -> int:
        """Return the number of bands."""
        count = self.src.RasterCount
        self._count = count
        return self._count

    @property
    @BaseIO.check_state
    def srs(
        self,
    ) -> osr.SpatialReference:
        """Return the srs (Spatial Reference System)."""
        _srs = self.src.GetSpatialRef()
        if _srs is None:
            _srs = self._srs
        return _srs

    @srs.setter
    def srs(
        self,
        srs,
    ):
        self._srs = srs

    @property
    @BaseIO.check_state
    def subdatasets(self):
        """Return the sub datasets of the source, if present."""
        return read_gridsource_layers(self.src)

    # Basic I/O methods
    def close(self):
        """Close the GridIO."""
        BaseIO.close(self)

        self._srs = None
        self.src = None
        self.driver = None

        gc.collect()

    def flush(self):
        """Flush the data.

        This only serves a purpose in write mode (`mode = 'w'`).
        """
        if self.src is not None:
            self.src.FlushCache()

    def reopen(self):
        """Reopen a closed GridIO."""
        if not self._closed:
            return self
        obj = GridIO.__new__(
            GridIO,
            file=self.path,
            chunk=self.chunk,
            subset=self.subset,
            var_as_band=self.var_as_band,
        )
        obj.__init__(
            file=self.path,
            chunk=self.chunk,
            subset=self.subset,
            var_as_band=self.var_as_band,
        )
        return obj

    ## Specific I/O methods
    @BaseIO.check_mode
    @BaseIO.check_state
    def create(
        self,
        shape: tuple,
        nb: int,
        type: int,
        options: list = [],
    ):
        """Create a new data source.

        Only in write (`'w'`) mode.

        Parameters
        ----------
        shape : tuple
            Shape of the grid. Takes the form of [<x-length>, <y-length>].
        nb : int
            The number of bands in the new data source.
        type : int
            Data type. The values is an integer which is linked to a data type
            recognized by GDAL. See [this page]
            (https://gdal.org/java/org/gdal/gdalconst/
            gdalconstConstants.html#GDT_Unknown) for more information.
        options : list
            Additional arguments.
        """
        self.src = self.driver.Create(
            self.path.as_posix(),
            *shape,
            nb,
            type,
            options=options,
        )

        self._count = nb

    @BaseIO.check_mode
    @BaseIO.check_state
    def create_band(
        self,
    ):
        """Create a new band.

        Only in write (`'w'`) mode.

        This will append the numbers of bands.
        """
        self.src.AddBand()
        self._count += 1

    @BaseIO.check_state
    def get_band_name(self, n: int) -> str:
        """Get the name of a specific band.

        Parameters
        ----------
        n : int
            Band number.

        Returns
        -------
        str
            Name of the band.
        """
        _desc = self[n].description
        _meta = self[n].meta

        if _desc:
            return _desc

        _var_meta = [item for item in _meta if "VARNAME" in item]

        if _var_meta:
            return _meta[_var_meta[0]]

        return ""

    @BaseIO.check_mode
    def set_geotransform(self, affine: tuple):
        """Set the geo transform of the grid.

        Parameters
        ----------
        affine : tuple
            An affine matrix.
        """
        self.src.SetGeoTransform(affine)

    @BaseIO.check_mode
    @BaseIO.check_state
    def set_srs(
        self,
        srs: osr.SpatialReference,
    ):
        """Set the srs of the gird.

        Only in write (`'w'`) mode.

        This is the spatial reference system defined by GDAL.

        Parameters
        ----------
        srs : osr.SpatialReference
            The srs.
        """
        self.src.SetSpatialRef(srs)
