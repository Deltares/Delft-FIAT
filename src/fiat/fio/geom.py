"""Basic I/O for vector files using OGR."""

import gc
from pathlib import Path

from osgeo import gdal, ogr, osr

from fiat.error import DriverNotFoundError
from fiat.fio.base import BaseIO
from fiat.struct import GeomStruct
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
    file : str
        Path to a file.
    mode : str, optional
        The I/O mode. Either `r` for reading or `w` for writing.
    overwrite : bool, optional
        Whether or not to overwrite an existing dataset.
    srs : str, optional
        A Spatial reference system string in case the dataset has none.

    Examples
    --------
    Index the GeomSource directly to get features.
    ```Python
    # Load a file
    gm = GeomSource(< path-to-file >)

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
        file: str,
        mode: str = "r",
        overwrite: bool = False,
        srs: str | None = None,
    ):
        BaseIO.__init__(self, file, mode)

        if mode == "r":
            _map = GEOM_READ_DRIVER_MAP
        else:
            _map = GEOM_WRITE_DRIVER_MAP

        if self.path.suffix not in _map:
            raise DriverNotFoundError(gog="Geometry", path=self.path)

        driver = _map[self.path.suffix]

        self.driver = ogr.GetDriverByName(driver)
        info = gdal.VSIStatL(self.path.as_posix())

        if (self.path.exists() or info is not None) and not overwrite:
            self.src = self.driver.Open(self.path.as_posix(), self.mode)
        else:
            if not self.mode:
                raise OSError(f"Cannot create {self.path} in 'read' mode.")
            self.create(self.path)

        info = None
        self._layer = None
        self._srs = None

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
    def layer(self):
        """Return the geometries layer."""
        if self._layer is not None:
            return self._layer
        obj = self.src.GetLayer()
        if obj is not None:
            self._layer = GeomStruct._create(self.src, obj, self.mode)
            return self._layer

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
        """Reopen a closed GeomSource."""
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
        self._layer = GeomStruct._create(self.src, obj, self.mode)

    @BaseIO.check_mode
    @BaseIO.check_state
    def create_layer_from_copy(
        self,
        layer: ogr.Layer,
        overwrite: bool = True,
    ):
        """Create a new layer by copying another layer.

        Only in write (`'w'`) mode.

        Parameters
        ----------
        layer : ogr.Layer
            A layer defined by OGR.
        overwrite : bool, optional
            If set to `True`, it will overwrite an existing layer.
        """
        _ow = {
            True: "YES",
            False: "NO",
        }

        obj = self.src.CopyLayer(layer, self.path.stem, [f"OVERWRITE={_ow[overwrite]}"])
        self._layer = GeomStruct._create(self.src, obj, self.mode)

    @BaseIO.check_mode
    @BaseIO.check_state
    def copy_layer(
        self,
        layer: ogr.Layer,
        layer_fn: str,
    ):
        """Copy a layer to an existing dataset.

        Bit of a spoof off of `create_layer_from_copy`.
        This method is a bit more forcing and allows to set it's own variable as
        layer name.
        Only in write (`'w'`) mode.

        Parameters
        ----------
        layer : ogr.Layer
            _description_
        layer_fn : str
            _description_
        """
        obj = self.src.CopyLayer(layer, layer_fn, ["OVERWRITE=YES"])
        self._layer = GeomStruct._create(self.src, obj, self.mode)

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
        self._layer = None
        self.src.DeleteLayer(self.path.stem)
        if all:
            self.driver.DeleteDataSource(self.path.as_posix())
            self.src = None
