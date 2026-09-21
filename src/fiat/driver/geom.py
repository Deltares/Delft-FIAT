"""Basic I/O for vector files using OGR."""

import gc
import weakref
from pathlib import Path
from typing import Generator

from osgeo import gdal, ogr, osr
from pyproj import CRS

from fiat.driver.base import BaseDriver, BaseStruct
from fiat.error import DriverNotFoundError
from fiat.util import (
    GEOM_DRIVER_MAP,
)

__all__ = ["GeomDriver", "GeomLayer"]


class GeomLayer(BaseStruct):
    """Geometries source object.

    Used to access and modify the features in a layer.
    """

    def __init__(self, *args, **kwargs):
        # For typing
        self._obj: ogr.Layer | None = None
        self._obj_ref: weakref.ReferenceType | None = None
        self._count: int = 0
        self.mode: int = 0
        raise AttributeError("No constructer defined")

    @classmethod
    def _create(
        cls,
        ref: gdal.Dataset,
        layer: ogr.Layer,
        mode: int,
    ) -> "GeomLayer":
        # This is effectively the init methods of this class
        obj = GeomLayer.__new__(cls)
        BaseStruct.__init__(obj)

        # Set the content
        obj._obj_ref = weakref.ref(ref, obj._cleanup)
        obj._obj = layer
        obj._count = obj.size
        obj.mode = mode

        # Fill out some info
        obj._retrieve_columns()

        return obj

    def __del__(self):
        self._obj = None

    def __iter__(self):
        self._obj.ResetReading()
        self._cur_index = 0
        return self

    def __next__(self) -> ogr.Feature:
        if self._cur_index < self._count:
            r = self._obj.GetNextFeature()
            self._cur_index += 1
            return r
        else:
            raise StopIteration

    def __getitem__(self, fid) -> ogr.Feature:
        return self._obj.GetFeature(fid)

    ## Some private methods
    def _cleanup(self, weak_ref) -> None:
        self._obj = None

    def _retrieve_columns(self) -> None:
        """Get the column headers from the swig object."""
        # Reset the columns to an empty dict
        self._columns = {}

        # Loop through the fields
        for idx, n in enumerate(self.fields):
            self._columns[n] = idx

    def reduced_iter(
        self,
        si: int,
        ei: int,
    ) -> Generator[ogr.Feature, None, None]:
        """Yield items on an interval.

        Creates a python generator.

        Parameters
        ----------
        si : int
            Starting index.
        ei : int
            Ending index.

        Returns
        -------
        ogr.Feature
            Features from the vector layer.
        """
        _c = 1
        for ft in self._obj:
            if si <= _c <= ei:
                yield ft
            _c += 1

    ## Properties
    @property
    def ref(self) -> weakref.ReferenceType:
        """Return the source reference."""
        return self._obj_ref()

    @property
    def bounds(self) -> tuple:
        """Return the bounds of the Dataset.

        Returns
        -------
        list
            Contains the four boundaries of the grid. This take the form of \
[left, bottom, right, top]
        """
        b = self._obj.GetExtent()
        return (b[0], b[2], b[1], b[3])

    @property
    def columns(self) -> tuple:
        """Return the columns header of the attribute tabel.

        (Same as field, but determined from internal _columns attribute)

        Returns
        -------
        tuple
            Attribute table headers
        """
        return tuple(self._columns.keys())

    @property
    def crs(self) -> CRS:
        """Return the crs (Spatial Reference System)."""
        ref = self._obj.GetSpatialRef()
        if ref is not None:
            return CRS.from_user_input(ref.ExportToWkt())
        return None

    @property
    def defn(self) -> ogr.FeatureDefn:
        """Return the layer definition."""
        return self._obj.GetLayerDefn()

    @property
    def dtypes(self) -> list[int]:
        """Return the data types of the fields."""
        _flds = self._obj.GetLayerDefn()
        dt = [_flds.GetFieldDefn(_i).type for _i in range(_flds.GetFieldCount())]
        _flds = None
        return dt

    @property
    def fields(self) -> list[str]:
        """Return the names of the fields."""
        _flds = self._obj.GetLayerDefn()
        fh = [_flds.GetFieldDefn(_i).GetName() for _i in range(_flds.GetFieldCount())]
        _flds = None
        return fh

    @property
    def geom_type(self) -> int:
        """Return the geometry type."""
        return self._obj.GetGeomType()

    @property
    def name(self) -> str:
        """Return the layer name."""
        return self._obj.GetName()

    @property
    def size(self) -> int:
        """Return the size (geometry count)."""
        count = self._obj.GetFeatureCount()
        self._count = count
        return self._count

    ## Set methods
    def add_feature(
        self,
        ft: ogr.Feature,
    ):
        """Add a feature to the layer.

        Only in write (`'w'`) mode.

        Note! Everything needs to already be compliant with the created/ edited
        dataset.

        Parameters
        ----------
        ft : ogr.Feature
            A feature object defined by OGR.
        """
        self._obj.CreateFeature(ft)

    def add_feature_with_map(
        self,
        in_ft: ogr.Feature,
        fmap: zip,
    ):
        """Add a feature with extra field data.

        Parameters
        ----------
        in_ft : ogr.Feature
            The feature to be added.
        fmap : zip
            Extra fields data, i.e. a zip object of fields id's
            and the corresponding values.
        """
        ft = ogr.Feature(self.defn)
        ft.SetFrom(in_ft)

        for key, item in fmap:
            ft.SetField(key, item)

        self._obj.CreateFeature(ft)
        ft = None

    def create_field(
        self,
        name: str,
        type: int,
    ):
        """Add a new field.

        Only in write (`'w'`) mode.

        Parameters
        ----------
        name : str
            Name of the new field.
        type : int
            Type of the new field.
        """
        self._obj.CreateField(
            ogr.FieldDefn(
                name,
                type,
            )
        )
        self._retrieve_columns()

    def create_fields(
        self,
        fmap: dict,
    ):
        """Add multiple fields at once.

        Only in write (`'w'`) mode.

        Parameters
        ----------
        fmap : dict
            A dictionary where the keys are the names of the new fields and the values
            are the data types of the new field.
        """
        self._obj.CreateFields([ogr.FieldDefn(key, item) for key, item in fmap.items()])
        self._retrieve_columns()

    def set_from_defn(
        self,
        defn: ogr.FeatureDefn,
    ):
        """Set layer meta from another layer's meta.

        Only in write (`'w'`) mode.

        Parameters
        ----------
        ref : ogr.FeatureDefn
            The definition of a layer. Defined by OGR.
        """
        for n in range(defn.GetFieldCount()):
            self._obj.CreateField(defn.GetFieldDefn(n))


class GeomDriver(BaseDriver):
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
    crs : str, optional
        A Spatial reference system string in case the dataset has none.

    Examples
    --------
    Index the GeomDriver directly to get features.
    ```Python
    # Load a file
    gm = GeomDriver(< path-to-file >)

    # Index it!
    feature = gm.layer[1]
    ```
    """

    def __new__(
        cls,
        file: str,
        mode: str = "r",
        overwrite: bool = False,
        crs: str | None = None,
    ):
        """Create a GeomDriver object."""
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
    def crs(self) -> CRS | None:
        """Return the crs (Spatial Reference System)."""
        _crs = self.layer.crs or self._crs
        if _crs is not None:
            return CRS.from_user_input(_crs)
        return None

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

        self._crs = None
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
    ) -> "GeomDriver":
        """Reopen a closed GeomDriver."""
        if not self.closed:
            return self
        obj = GeomDriver.__new__(GeomDriver, self.path, mode=mode)
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
