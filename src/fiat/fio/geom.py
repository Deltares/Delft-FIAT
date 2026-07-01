"""Basic I/O for vector files using OGR."""

import gc
from pathlib import Path

from osgeo import gdal, ogr, osr
from pyproj import CRS

from fiat.error import DriverNotFoundError
from fiat.fio.base import BaseDriver
from fiat.struct import GeomLayer
from fiat.util import (
    GEOM_DRIVER_MAP,
)

__all__ = ["GeomIO"]


class GeomIO(BaseDriver):
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
    feature = gm.layer[1]
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
        crs: str | None = None,
    ):
        self._crs = crs
        self.src: gdal.Dataset = None
        # Supercharge
        BaseDriver.__init__(self, file, mode)

        # Check for the driver
        if self.path.suffix not in GEOM_DRIVER_MAP:
            raise DriverNotFoundError(gog="Geometry", path=self.path)

        # Set the driver and retrieve info
        driver: str = GEOM_DRIVER_MAP[self.path.suffix]
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

    def __reduce__(self):
        return self.__class__, (
            self.path,
            self.mode_str,
            False,
            self._crs,
        )

    ## Properties
    @property
    @BaseDriver.check_state
    def crs(self) -> CRS:
        """Return the crs (Spatial Reference System)."""
        _crs = self.layer.crs
        if _crs is None:
            _crs = self._crs
        return CRS.from_user_input(_crs)

    @crs.setter
    def crs(self, value: str):
        self._crs = value

    @property
    @BaseDriver.check_state
    def driver_meta(self) -> dict:
        """Return the driver meta data."""
        return self.driver.GetMetadata()

    @property
    @BaseDriver.check_state
    def layer(self) -> GeomLayer:
        """Return the geometries layer."""
        if self._layer is not None:
            return self._layer
        obj = self.src.GetLayer()
        if obj is not None:
            self._layer = GeomLayer._create(self.src, obj, self.mode)
            return self._layer

    ## Basic I/O methods
    def close(self) -> None:
        """Close the dataset."""
        BaseDriver.close(self)
        if self.src is not None:
            self.src.Close()

        self._srs = None
        self._layer = None
        self.src = None
        self.driver = None

        gc.collect()

    def flush(self) -> None:
        """Flush the buffer.

        This only serves a purpose in write mode (`mode = 'w'`).
        """
        if self.src is not None:
            self.src.FlushCache()

    def reopen(
        self,
        mode: str = "r",
    ) -> "GeomIO":
        """Reopen a closed GeomIO."""
        if not self.closed:
            return self
        obj = GeomIO.__new__(GeomIO, self.path, mode=mode)
        obj.__init__(self.path, mode=mode)
        return obj

    ## Specific I/O methods
    @BaseDriver.check_mode
    @BaseDriver.check_state
    def create(
        self,
        path: Path | str,
    ) -> None:
        """Create a data source.

        Parameters
        ----------
        path : Path | str
            Path to the data source.
        """
        self.src = None
        path = Path(path)  # Ensure typing
        self.src = self.driver.CreateDataSource(path.as_posix())
        self.path = path  # Overwrite the path

    @BaseDriver.check_mode
    @BaseDriver.check_state
    def create_layer(
        self,
        crs: CRS | str,
        geom_type: int,
    ) -> None:
        """Create a new vector layer.

        Only in write (`'w'`) mode.

        Parameters
        ----------
        crs : CRS | str
            Spatial Reference System.
        geom_type : int
            Type of geometry. E.g. 'POINT' or 'POLYGON'. It is supplied as an integer
            that complies with a specific geometry type according to GDAL.
        """
        srs = osr.SpatialReference()
        srs.SetFromUserInput(CRS.from_user_input(crs).to_wkt())
        obj = self.src.CreateLayer(self.path.stem, srs, geom_type)
        self._layer = GeomLayer._create(self.src, obj, self.mode)
        srs = None

    @BaseDriver.check_mode
    @BaseDriver.check_state
    def delete(
        self,
        all=False,
    ) -> None:
        """Delete the vector layer.

        Parameters
        ----------
        all : bool, optional
            Delete everything, including the data source, by default False
        """
        check = self._layer is not None and not all
        if check and gdal.DCAP_DELETE_LAYER in self.driver_meta:
            name = self.layer.name
            self._layer = None
            self.src.DeleteLayer(name)
        if all:
            self._layer = None
            self.src = None
            self.driver.Delete(self.path.as_posix())
