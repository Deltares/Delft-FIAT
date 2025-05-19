"""A python wrapper structure for gdal Band."""

import weakref

from numpy import ndarray
from osgeo import gdal

from fiat.struct.base import BaseStruct


class GridBand(
    BaseStruct,
):
    """A source object for a specific raster band.

    Acquired by indexing a GridIO object.

    Parameters
    ----------
    band : gdal.Band
        A band defined by GDAL.
    chunk : tuple, optional
        Chunk size in x direction and y direction.
    mode : str, optional
        The I/O mode. Either `r` for reading or `w` for writing.
    """

    def __init__(self, *args, **kwargs):
        # For typing
        self._obj: gdal.Band = None
        self._x: int = None
        self._y: int = None
        self._l: int = None
        self._u: int = None
        self.mode: int = None
        self.nodata: float | int = None
        self.dtype: int = None
        self.dtype_name: str = None
        self.dtype_size: int = None
        raise AttributeError("No constructer defined")

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
        chunk = self._obj.ReadAsArray(*window)
        return chunk

    @classmethod
    def _create(
        cls,
        ref: gdal.Dataset,
        band: gdal.Band,
        chunk: tuple,
        mode: int,
    ):
        # This is effectively the init methods of this class
        obj = GridBand.__new__(cls)
        super(BaseStruct, obj).__init__()

        # Set the content
        obj._obj_ref = weakref.ref(ref, obj._cleanup)
        obj._obj = band
        obj._x = band.XSize
        obj._y = band.YSize
        obj._l = 0
        obj._u = 0
        obj.mode = mode
        obj.nodata = band.GetNoDataValue()
        obj.dtype = band.DataType
        obj.dtype_name = gdal.GetDataTypeName(obj.dtype)
        obj.dtype_size = gdal.GetDataTypeSize(obj.dtype)

        obj._chunk = obj.shape
        if chunk is not None:
            obj.chunk = chunk

        return obj

    def __del__(self):
        self._obj = None

    ## Some private methods
    def _cleanup(self, weak_ref):
        self._obj = None

    def _reset_chunking(self):
        self._l = 0
        self._u = 0

    def flush(self):
        """Flush the grid object."""
        if self._obj is not None:
            self._obj.FlushCache()

    ## Properties
    @property
    def ref(self):
        """Return the source reference."""
        return self._obj_ref()

    @property
    def chunk(self) -> tuple:
        """Return the chunk size."""
        return self._chunk

    @chunk.setter
    def chunk(self, value: tuple[int]):
        """Set the chunk size."""
        if len(value) != 2:
            raise ValueError("Chunk should have two elements")
        self._chunk = value

    @property
    def description(self) -> str:
        """Return the band description."""
        return self._obj.GetDescription()

    @property
    def meta(self) -> dict:
        """Return the band meta data."""
        return self._obj.GetMetadata()

    @property
    def shape(self) -> tuple:
        """Return the shape of the grid.

        According to normal reading, i.e. rows, columns.

        Returns
        -------
        tuple
            Size in y direction, size in x direction
        """
        return self._y, self._x

    @property
    def shape_xy(self) -> tuple:
        """Return the shape of the grid.

        According to x-direction first.

        Returns
        -------
        tuple
            Size in x direction, size in y direction
        """
        return self._x, self._y

    ## get/ set methods
    def get_metadata_item(
        self,
        entry: str,
    ) -> object:
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
        res = str(self._obj.GetMetadataItem(entry))
        return res

    def write_chunk(
        self,
        chunk: ndarray,
        upper_left: tuple | list,
    ):
        """Write a chunk of data to the band.

        Only in write (`'w'`) mode.

        Parameters
        ----------
        chunk : ndarray
            Array of data.
        upper_left : tuple | list
            Upper left corner of the chunk.
            N.b. these are not coordinates, but indices.
        """
        self._obj.WriteArray(chunk, *upper_left)
