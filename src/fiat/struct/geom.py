"""A python wrapper structure for ogr Layer."""

import weakref

from osgeo import gdal, ogr, osr

from fiat.struct.base import BaseStruct

__all__ = ["GeomLayer"]


class GeomLayer(BaseStruct):
    """Geometries container."""

    def __init__(self, *args, **kwargs):
        # For typing
        self._obj: ogr.Layer | None = None
        self._count: int = 0
        self.mode: int = 0
        raise AttributeError("No constructer defined")

    @classmethod
    def _create(
        cls,
        ref: gdal.Dataset,
        layer: ogr.Layer,
        mode: int,
    ):
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

    def __next__(self):
        if self._cur_index < self._count:
            r = self._obj.GetNextFeature()
            self._cur_index += 1
            return r
        else:
            raise StopIteration

    def __getitem__(self, fid) -> ogr.Feature:
        return self._obj.GetFeature(fid)

    ## Some private methods
    def _cleanup(self, weak_ref):
        self._obj = None

    def _retrieve_columns(self):
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
    ):
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
    def ref(self):
        """Return the source reference."""
        return self._obj_ref()

    @property
    def bounds(self) -> tuple:
        """Return the bounds of the GridIO.

        Returns
        -------
        list
            Contains the four boundaries of the grid. This take the form of \
[left, right, top, bottom]
        """
        return self._obj.GetExtent()

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

    @property
    def srs(self) -> osr.SpatialReference:
        """Return the srs (Spatial Reference System)."""
        return self._obj.GetSpatialRef()

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
            and the correspondingv alues
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
