"""Basic I/O for raster files using GDAL."""

import gc
from pathlib import Path

from numpy import array
from osgeo import gdal, osr

from fiat.error import DriverNotFoundError
from fiat.fio.base import BaseIO
from fiat.struct.base import BaseStruct
from fiat.util import (
    GRID_DRIVER_MAP,
    get_srs_repr,
    read_gridsource_layers,
)

__all__ = ["Grid", "GridSource"]


class Grid(
    BaseIO,
    BaseStruct,
):
    """A source object for a specific raster band.

    Acquired by indexing a GridSource object.

    Parameters
    ----------
    band : gdal.Band
        A band defined by GDAL.
    chunk : tuple, optional
        Chunk size in x direction and y direction.
    mode : str, optional
        The I/O mode. Either `r` for reading or `w` for writing.
    """

    def __init__(
        self,
        band: gdal.Band,
        chunk: tuple = None,
        mode: str = "r",
    ):
        BaseIO.__init__(self, mode=mode)

        self.src = band
        self._x = band.XSize
        self._y = band.YSize
        self._l = 0
        self._u = 0
        self.nodata = band.GetNoDataValue()
        self.dtype = band.DataType
        self.dtype_name = gdal.GetDataTypeName(self.dtype)
        self.dtype_size = gdal.GetDataTypeSize(self.dtype)

        self._last_chunk = None

        if chunk is None:
            self._chunk = self.shape
        elif len(chunk) == 2:
            self._chunk = chunk
        else:
            raise ValueError(f"Incorrect chunking set: {chunk}")

    def __iter__(self):
        self.flush()
        self._reset_chunking()
        return self

    def __next__(self):
        if self._u > self._y:
            self.flush()
            raise StopIteration

        w = min(self._chunk[1], self._x - self._l)
        h = min(self._chunk[0], self._y - self._u)

        window = (
            self._l,
            self._u,
            w,
            h,
        )
        chunk = self[window]

        self._l += self._chunk[1]
        if self._l > self._x:
            self._l = 0
            self._u += self._chunk[0]

        return window, chunk

    def __getitem__(
        self,
        window: tuple,
    ):
        chunk = self.src.ReadAsArray(*window)
        return chunk

    def _reset_chunking(self):
        self._l = 0
        self._u = 0

    def close(self):
        """Close the Grid object."""
        BaseIO.close(self)
        self.src = None
        gc.collect()

    def flush(self):
        """Flush the grid object."""
        if self.src is not None:
            self.src.FlushCache()

    @property
    def chunk(self):
        """Return the chunk size."""
        return self._chunk

    @property
    def shape(self):
        """Return the shape of the grid.

        According to normal reading, i.e. rows, columns.

        Returns
        -------
        tuple
            Size in y direction, size in x direction
        """
        return self._y, self._x

    @property
    def shape_xy(self):
        """Return the shape of the grid.

        According to x-direction first.

        Returns
        -------
        tuple
            Size in x direction, size in y direction
        """
        return self._x, self._y

    def get_metadata_item(
        self,
        entry: str,
    ):
        """Get specific metadata item.

        Parameters
        ----------
        entry : str
            Identifier of item.

        Returns
        -------
        object
            Information is present.
        """
        res = str(self.src.GetMetadataItem(entry))
        return res

    def set_chunk_size(
        self,
        chunk: tuple,
    ):
        """Set the chunking size.

        Parameters
        ----------
        chunk : tuple
            Size in x direction, size in y direction.
        """
        self._chunk = chunk

    @BaseIO.check_mode
    def write_chunk(
        self,
        chunk: array,
        upper_left: tuple | list,
    ):
        """Write a chunk of data to the band.

        Only in write (`'w'`) mode.

        Parameters
        ----------
        chunk : array
            Array of data.
        upper_left : tuple | list
            Upper left corner of the chunk.
            N.b. these are not coordinates, but indices.
        """
        self.src.WriteArray(chunk, *upper_left)


class GridSource(BaseIO, BaseStruct):
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
    Can be indexed directly to get a `Grid` object.
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
        """Create a new GridSource object."""
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
        _open_options = []

        BaseStruct.__init__(self)
        self._update_kwargs(
            subset=subset,
            var_as_band=var_as_band,
        )

        BaseIO.__init__(self, file, mode)

        if self.path.suffix not in GRID_DRIVER_MAP:
            raise DriverNotFoundError(gog="Grid", path=self.path)

        driver = GRID_DRIVER_MAP[self.path.suffix]

        if not subset:
            subset = None
        self.subset = subset

        if subset is not None and not var_as_band:
            self._path = Path(
                f"{driver.upper()}:" + f'"{file}"' + f":{subset}",
            )

        if var_as_band:
            _open_options.append("VARIABLES_AS_BANDS=YES")
        self._var_as_band = var_as_band

        self._driver = gdal.GetDriverByName(driver)

        self.src = None
        self._chunk = None
        self._dtype = None
        self.subset_dict = None
        self._count = 0
        self._cur_index = 1
        self._srs = None
        if srs is not None:
            self._srs = osr.SpatialReference()
            self._srs.SetFromUserInput(srs)

        if not self.mode:
            self.src = gdal.OpenEx(self._path.as_posix(), open_options=_open_options)
            self._count = self.src.RasterCount

            if chunk is None:
                self._chunk = self.shape
            elif len(chunk) == 2:
                self._chunk = chunk
            else:
                raise ValueError(f"Incorrect chunking set: {chunk}")

            if self._count == 0:
                self.subset_dict = read_gridsource_layers(
                    self.src,
                )

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
    ):
        return Grid(
            self.src.GetRasterBand(oid),
            chunk=self.chunk,
            mode=self.mode_str,
        )

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
            self._var_as_band,
        )

    def close(self):
        """Close the GridSource."""
        BaseIO.close(self)

        self.src = None
        self._srs = None
        self._driver = None

        gc.collect()

    def flush(self):
        """Flush the data.

        This only serves a purpose in write mode (`mode = 'w'`).
        """
        if self.src is not None:
            self.src.FlushCache()

    def reopen(self):
        """Reopen a closed GridSource."""
        if not self._closed:
            return self
        obj = GridSource.__new__(
            GridSource,
            file=self.path,
            chunk=self.chunk,
            subset=self.subset,
            var_as_band=self._var_as_band,
        )
        obj.__init__(
            file=self.path,
            chunk=self._chunk,
            subset=self.subset,
            var_as_band=self._var_as_band,
        )
        return obj

    @property
    @BaseIO.check_state
    def bounds(self):
        """Return the bounds of the GridSource.

        Returns
        -------
        list
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
    def chunk(self):
        """Return the chunking size.

        Returns
        -------
        list
            The chunking in x direction and y direction.
        """
        return self._chunk

    @property
    @BaseIO.check_state
    def dtype(self):
        """Return the data types of the field data."""
        if not self._dtype:
            _b = self[1]
            self._dtype = _b.dtype
            del _b
        return self._dtype

    @property
    @BaseIO.check_state
    def geotransform(self):
        """Return the geo transform of the grid."""
        return self.src.GetGeoTransform()

    @property
    @BaseIO.check_state
    def shape(self):
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
    def shape_xy(self):
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
    def size(self):
        """Return the number of bands."""
        count = self.src.RasterCount
        self._count = count
        return self._count

    @property
    @BaseIO.check_state
    def srs(
        self,
    ):
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
        self.src = self._driver.Create(
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
    def deter_band_names(
        self,
    ):
        """Determine the names of the bands.

        If the bands do not have any names of themselves,
        they will be set to a default.
        """
        _names = []
        for n in range(self.size):
            name = self.get_band_name(n + 1)
            if not name:
                _names.append(f"band{n+1}")
                continue
            _names.append(name)

        return _names

    @BaseIO.check_state
    def get_band_name(self, n: int):
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
        _desc = self[n].src.GetDescription()
        _meta = self[n].src.GetMetadata()

        if _desc:
            return _desc

        _var_meta = [item for item in _meta if "VARNAME" in item]

        if _var_meta:
            return _meta[_var_meta[0]]

        return ""

    def get_band_names(
        self,
    ):
        """Get the names of all bands."""
        _names = []
        for n in range(self.size):
            _names.append(self.get_band_name(n + 1))

        return _names

    def set_chunk_size(
        self,
        chunk: tuple,
    ):
        """Set the chunking size of the grid.

        Parameters
        ----------
        chunk : tuple
            A tuple containing the chunking size in x direction and y direction.
        """
        self._chunk = chunk

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
