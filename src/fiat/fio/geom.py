"""Basic I/O for vector files using OGR."""

import gc
from pathlib import Path

from osgeo import gdal, ogr, osr

from fiat.error import DriverNotFoundError
from fiat.fio.base import BaseIO
from fiat.struct import GeomLayer
from fiat.util import (
    GEOM_READ_DRIVER_MAP,
    GEOM_WRITE_DRIVER_MAP,
    get_srs_repr,
)

__all__ = ["GeomIO"]


class GeomIO(BaseIO):
    """A source object for geospatial vector data.

    Essentially an OGR DataSource wrapper.

    Parameters
    ----------
    file : Path | str
        Path to a file.
    mode : str, optional
        The I/O mode. Either `r` for reading or `w` for writing.
    overwrite : bool, optional
        Whether or not to overwrite an existing dataset.
    srs : str, optional
        A Spatial reference system string in case the dataset has none.

    Examples
    --------
    Index the GeomIO directly to get features.
    ```Python
    # Load a file
    gm = GeomIO(< path-to-file >)

    # Index it!
    feature = gm[1]
    ```
    """

    def __new__(
        cls,
        file: str,
        mode: str = "r",
        overwrite: bool = False,
        srs: str | None = None,
    ):
        """Create a GeomIO object."""
        obj = object.__new__(cls)

        return obj

    def __init__(
        self,
        file: Path | str,
        mode: str = "r",
        overwrite: bool = False,
        srs: str | None = None,
    ):
        self.src: gdal.Dataset = None
        # Supercharge
        BaseIO.__init__(self, file, mode)

        # Select the driver map based on the mode
        _map = GEOM_READ_DRIVER_MAP
        if self.mode == 2:
            _map = GEOM_WRITE_DRIVER_MAP

        # Check for the driver
        if self.path.suffix not in _map:
            raise DriverNotFoundError(gog="Geometry", path=self.path)

        # Set the driver and retrieve info
        driver: str = _map[self.path.suffix]
        self.driver: gdal.Driver = ogr.GetDriverByName(driver)

        # Read or create a data source depending on the mode
        if self.mode != 2 and not overwrite:
            self.src = gdal.OpenEx(
                self.path.as_posix(),
                nOpenFlags=self.mode,
            )
        elif self.mode == 2 or (self.mode == 1 and overwrite):
            self.create(self.path)

        self._layer: GeomLayer = None
        self._srs: osr.SpatialReference = None
        if srs is not None:
            self._srs = osr.SpatialReference()
            self._srs.SetFromUserInput(srs)

    def __reduce__(self):
        srs = None
        if self._srs is not None:
            srs = get_srs_repr(self._srs)
        return self.__class__, (
            self.path,
            self.mode_str,
            False,
            srs,
        )

    ## Properties
    @property
    @BaseIO.check_state
    def driver_meta(self):
        """Return the driver meta data."""
        return self.driver.GetMetadata()

    @property
    @BaseIO.check_state
    def layer(self) -> GeomLayer:
        """Return the geometries layer."""
        if self._layer is not None:
            return self._layer
        obj = self.src.GetLayer()
        if obj is not None:
            self._layer = GeomLayer._create(self.src, obj, self.mode)
            return self._layer

    @property
    @BaseIO.check_state
    def srs(self) -> osr.SpatialReference:
        """Return the srs (Spatial Reference System)."""
        _srs = self.layer.srs
        if _srs is None:
            _srs = self._srs
        return _srs

    @srs.setter
    def srs(self, srs: osr.SpatialReference):
        self._srs = srs

    ## Basic I/O methods
    def close(self):
        """Close the dataset."""
        BaseIO.close(self)
        if self.src is not None:
            self.src.Close()

        self._srs = None
        self._layer = None
        self.src = None
        self.driver = None

        gc.collect()

    def flush(self):
        """Flush the buffer.

        This only serves a purpose in write mode (`mode = 'w'`).
        """
        if self.src is not None:
            self.src.FlushCache()

    def reopen(
        self,
        mode: str = "r",
    ):
        """Reopen a closed GeomIO."""
        if not self.closed:
            return self
        obj = GeomIO.__new__(GeomIO, self.path, mode=mode)
        obj.__init__(self.path, mode=mode)
        return obj

    ## Specific I/O methods
    @BaseIO.check_mode
    @BaseIO.check_state
    def create(
        self,
        path: Path | str,
    ):
        """Create a data source.

        Parameters
        ----------
        path : Path | str
            Path to the data source.
        """
        self.src = None
        self.src = self.driver.CreateDataSource(path.as_posix())

    @BaseIO.check_mode
    @BaseIO.check_state
    def create_layer(
        self,
        srs: osr.SpatialReference,
        geom_type: int,
    ):
        """Create a new vector layer.

        Only in write (`'w'`) mode.

        Parameters
        ----------
        srs : osr.SpatialReference
            Spatial Reference System.
        geom_type : int
            Type of geometry. E.g. 'POINT' or 'POLYGON'. It is supplied as an integer
            that complies with a specific geometry type according to GDAL.
        """
        obj = self.src.CreateLayer(self.path.stem, srs, geom_type)
        self._layer = GeomLayer._create(self.src, obj, self.mode)

    @BaseIO.check_mode
    @BaseIO.check_state
    def delete(
        self,
        all=False,
    ):
        """Delete the vector layer.

        Parameters
        ----------
        all : bool, optional
            Delete everything, including the data source, by default False
        """
        check = self._layer is not None
        if check and gdal.DCAP_DELETE_LAYER in self.driver_meta:
            name = self.layer.name
            self._layer = None
            self.src.DeleteLayer(name)
        if all:
            self._layer = None
            self.src = None
            self.driver.Delete(self.path.as_posix())
