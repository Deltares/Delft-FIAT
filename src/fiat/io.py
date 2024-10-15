"""Where I/O stuff gets handled."""

import atexit
import gc
import os
import weakref
from abc import ABCMeta, abstractmethod
from io import BufferedReader, BytesIO, FileIO
from math import floor, log10
from multiprocessing.synchronize import Lock
from pathlib import Path
from typing import Any

from numpy import arange, array, column_stack, interp, ndarray
from osgeo import gdal, ogr, osr
from osgeo_utils.ogrmerge import process as ogr_merge

from fiat.error import DriverNotFoundError
from fiat.util import (
    DD_NEED_IMPLEMENTED,
    DD_NOT_IMPLEMENTED,
    GEOM_READ_DRIVER_MAP,
    GEOM_WRITE_DRIVER_MAP,
    GRID_DRIVER_MAP,
    NEED_IMPLEMENTED,
    NEWLINE_CHAR,
    NOT_IMPLEMENTED,
    DummyLock,
    _dtypes_from_string,
    _dtypes_reversed,
    _read_gridsrouce_layers,
    _text_chunk_gen,
    deter_type,
    find_duplicates,
    regex_pattern,
    replace_empty,
)

_IOS = weakref.WeakValueDictionary()
_IOS_COUNT = 1

gdal.AllRegister()


def _add_ios_ref(wref):
    global _IOS_COUNT
    _IOS_COUNT += 1
    pass


def _DESTRUCT():
    items = list(_IOS.items())
    for _, item in items:
        item.close()
        del item


atexit.register(_DESTRUCT)


## Base
class _BaseIO(metaclass=ABCMeta):
    _mode_map = {
        "r": 0,
        "w": 1,
    }

    _closed = False
    _path = None
    path = None
    src = None

    def __init__(
        self,
        file: str = None,
        mode: str = "r",
    ):
        """_summary_."""
        if file is not None:
            self.path = Path(file)
            self._path = Path(file)

        if mode not in _BaseIO._mode_map:
            raise ValueError("")

        self._mode = _BaseIO._mode_map[mode]
        self._mode_str = mode

    def __del__(self):
        if not self._closed:
            self.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def _check_mode(m):
        def _inner(self, *args, **kwargs):
            if not self._mode:
                raise ValueError("Invalid operation on a read-only file")
            _result = m(self, *args, **kwargs)

            return _result

        return _inner

    def _check_state(m):
        def _inner(self, *args, **kwargs):
            if self.closed:
                raise ValueError("Invalid operation on a closed file")
            _result = m(self, *args, **kwargs)

            return _result

        return _inner

    def close(self):
        self.flush()
        self._closed = True
        gc.collect()

    @property
    def closed(self):
        return self._closed

    @abstractmethod
    def flush(self):
        raise NotImplementedError(NEED_IMPLEMENTED)


class _BaseStruct(metaclass=ABCMeta):
    """A struct container."""

    def __init__(self):
        self._columns = {}
        self._kwargs = {}
        self._index = {}

    @abstractmethod
    def __del__(self):
        raise NotImplementedError(DD_NEED_IMPLEMENTED)

    def __repr__(self):
        _mem_loc = f"{id(self):#018x}".upper()
        return f"<{self.__class__.__name__} object at {_mem_loc}>"

    def _update_kwargs(
        self,
        **kwargs,
    ):
        """Update the keyword arguments.

        Only for internal use.
        """
        self._kwargs.update(
            **kwargs,
        )


## Handlers
class BufferHandler:
    """Handler for buffers."""

    def __init__(
        self,
        path: Path,
        skip: int = 0,
    ):
        self.path = path
        self.size = None
        self.skip = skip
        self.stream = None

        if self.stream is None:
            self.setup_stream()

    def __repr__(self):
        return f"<{self.__class__.__name__} file='{self.path}' encoding=''>"

    def __getstate__(self):
        if self.stream is not None:
            self.close_stream()
        return self.__dict__

    def __setstate__(self, d):
        self.__dict__ = d
        self.setup_stream()

    def __enter__(self):
        return self.stream.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stream.flush()
        self.stream.seek(self.skip)
        return False

    def close(self):
        """_summary_."""
        if self.stream is not None:
            self.stream.flush()
            self.close_stream()

    def close_stream(self):
        """_summary_."""
        self.stream.close()
        self.stream = None
        self.size = None

    def setup_stream(self):
        """_summary_."""
        self.stream = BufferedReader(FileIO(self.path))
        self.size = self.stream.read().count(os.linesep.encode())
        self.stream.seek(self.skip)


class BufferedGeomWriter:
    """_summary_."""

    def __init__(
        self,
        file: str | Path,
        srs: osr.SpatialReference,
        layer_defn: ogr.FeatureDefn = None,
        buffer_size: int = 100000,  # geometries
        lock: Lock = None,
    ):
        """_summary_.

        _extended_summary_

        Parameters
        ----------
        file : str | Path
            _description_
        srs : osr.SpatialReference
            _description_
        layer_meta : ogr.FeatureDefn
            _description_
        buffer_size : int, optional
            _description_, by default 20000
        """
        # Ensure pathlib.Path
        file = Path(file)
        self.file = file

        # Set the lock
        self.lock = lock
        if lock is None:
            self.lock = DummyLock()

        # Set for unique layer id's
        self.pid = os.getpid()

        # Set for later use
        self.srs = srs
        self.flds = {}
        self.n = 1

        if layer_defn is None:
            with open_geom(self.file, mode="r") as _r:
                layer_defn = _r.layer.GetLayerDefn()
            _r = None
        self.layer_defn = layer_defn

        # Create the buffer
        self.buffer = open_geom(f"/vsimem/{file.stem}.gpkg", "w")
        self.buffer.create_layer(
            srs,
            layer_defn.GetGeomType(),
        )
        self.buffer.set_layer_from_defn(
            layer_defn,
        )
        # Set some check vars
        # TODO: do this based om memory foodprint
        # Needs some reseach into ogr's memory tracking
        self.max_size = buffer_size
        self.size = 0

    def __del__(self):
        self.buffer = None
        self.layer_defn = None

    def __reduce__(self) -> str | tuple[Any, ...]:
        pass

    def _clear_cache(self):
        self.buffer.src.DeleteLayer(f"{self.file.stem}")
        self.buffer._driver.DeleteDataSource(f"/vsimem/{self.file.stem}.gpkg")

    def _reset_buffer(self):
        # Delete
        self.buffer.src.DeleteLayer(f"{self.file.stem}")

        # Re-create
        self.buffer.create_layer(
            self.srs,
            self.layer_defn.GetGeomType(),
        )
        self.buffer.set_layer_from_defn(
            self.layer_defn,
        )
        self.create_fields(self.flds)

        # Reset current size
        self.size = 0

    def close(self):
        """_summary_."""
        # Flush on last time
        self.to_drive()
        self._clear_cache()
        self.buffer.close()

    def add_feature_with_map(
        self,
        ft: ogr.Feature,
        fmap: dict,
    ):
        """_summary_."""
        self.buffer.add_feature_with_map(
            ft,
            fmap=fmap,
        )

        if self.size + 1 > self.max_size:
            self.to_drive()

        self.size += 1

    def create_fields(
        self,
        flds: zip,
    ):
        """_summary_."""
        _new = dict(flds)
        self.flds.update(_new)

        self.buffer.create_fields(
            _new,
        )

    def to_drive(self):
        """_summary_."""
        # Block while writing to the drive
        # self.buffer.close()
        self.lock.acquire()
        merge_geom_layers(
            self.file.as_posix(),
            f"/vsimem/{self.file.stem}.gpkg",
            out_layer_name=self.file.stem,
        )
        self.lock.release()

        # self.buffer = self.buffer.reopen(mode="w")
        self._reset_buffer()


class BufferedTextWriter(BytesIO):
    """_summary_."""

    def __init__(
        self,
        file: Path | str,
        mode: str = "wb",
        buffer_size: int = 524288,  # 512 kB
        lock: Lock = None,
    ):
        # Set the lock
        self.lock = lock
        if lock is None:
            self.lock = DummyLock()

        BytesIO.__init__(self)

        # Set object specific stuff
        self.stream = FileIO(
            file=file,
            mode=mode,
        )
        self.max_size = buffer_size

    def close(self):
        """_summary_."""
        # Flush on last time
        self.to_drive()
        self.stream.close()

        # Close the buffer
        BytesIO.close(self)

    def to_drive(self):
        """_summary_."""
        self.seek(0)

        # Push data to the file
        self.lock.acquire()
        self.stream.write(self.read())
        self.stream.flush()
        os.fsync(self.stream)
        self.lock.release()

        # Reset the buffer
        self.truncate(0)
        self.seek(0)

    def write(self, b):
        """_summary_.

        _extended_summary_

        Parameters
        ----------
        b : _type_
            _description_
        """
        if self.__sizeof__() + len(b) > self.max_size:
            self.to_drive()
        BytesIO.write(self, b)

    def write_iterable(self, *args):
        """_summary_.

        _extended_summary_
        """
        by = b""
        for arg in args:
            by += ("," + "{}," * len(arg)).format(*arg).rstrip(",").encode()
        by = by.lstrip(b",")
        by += NEWLINE_CHAR.encode()
        self.write(by)


## Parsing
class CSVParser:
    """_summary_."""

    def __init__(
        self,
        handler: BufferHandler,
        delimiter: str,
        header: bool,
        index: str = None,
    ):
        """_summary_."""
        self.delim = delimiter
        self.data = handler
        self.meta = {}
        self.meta["index_col"] = -1
        self.meta["index_name"] = None
        self.meta["delimiter"] = delimiter
        self.meta["dup_cols"] = None
        self.index = None
        self.columns = None
        self._nrow = self.data.size
        self._ncol = 0

        self._parse_meta(header)
        self._deter_dtypes_index(index=index)

    def _deter_dtypes_index(
        self,
        index: str,
    ):
        """_summary_."""
        _get_index = False
        _get_dtypes = True
        _pat_multi = regex_pattern(self.delim, multi=True)

        if index is not None:
            try:
                idcol = self.columns.index(index)
            except Exception:
                idcol = 0
            self.meta["index_col"] = idcol
            self.meta["index_name"] = self.columns[idcol]
            _index = []
            _get_index = True

        if "dtypes" in self.meta:
            _dtypes = self.meta["dtypes"]
            if len(_dtypes) != self._ncol:
                raise ValueError("")

            _dtypes = [_dtypes_from_string[item] for item in _dtypes]

            self.meta["dtypes"] = _dtypes
            _dtypes = None
            _get_dtypes = False

        if _get_dtypes or _get_index:
            if _get_dtypes:
                _dtypes = [0] * self._ncol
            with self.data as _h:
                for _nlines, sd in _text_chunk_gen(_h, pattern=_pat_multi):
                    if _get_dtypes:
                        for idx in range(self._ncol):
                            _dtypes[idx] = max(
                                deter_type(b"\n".join(sd[idx :: self._ncol]), _nlines),
                                _dtypes[idx],
                            )
                    if _get_index:
                        _index += sd[idcol :: self._ncol]
                    del sd

                if _get_dtypes:
                    self.meta["dtypes"] = [_dtypes_reversed[item] for item in _dtypes]
                if _get_index:
                    func = self.meta["dtypes"][idcol]
                    self.index = [func(item.decode()) for item in _index]

    def _parse_meta(
        self,
        header: bool,
    ):
        """_summary_."""
        _pat = regex_pattern(self.delim)
        self.data.stream.seek(0)

        while True:
            self._nrow -= 1
            cur_pos = self.data.stream.tell()
            line = self.data.stream.readline().decode("utf-8-sig")

            if line.startswith("#"):
                t = line.strip().split("=")
                if len(t) == 1:
                    tl = t[0].split(":")
                    if len(tl) > 1:
                        lst = tl[1].split(self.delim)
                        _entry = tl[0].strip().replace("#", "").lower()
                        _val = [item.strip() for item in lst]
                        self.meta[_entry] = _val
                    else:
                        lst = t[0].split(self.delim)
                        _entry = lst[0].strip().replace("#", "").lower()
                        _val = [item.strip() for item in lst[1:]]
                        self.meta[_entry] = _val
                        # raise ValueError("Supplied metadata in unknown format..")
                else:
                    key, item = t
                    self.meta[key.strip().replace("#", "").lower()] = item.strip()
                continue

            if not header:
                self.columns = None
                self._ncol = len(_pat.split(line.encode("utf-8-sig")))
                self.data.stream.seek(cur_pos)
                self._nrow += 1
                break

            self.columns = [item.strip() for item in line.split(self.delim)]
            self.meta["dup_cols"] = find_duplicates(self.columns)
            self._resolve_column_headers()
            self._ncol = len(self.columns)
            break

        self.data.skip = self.data.stream.tell()
        self.meta["ncol"] = self._ncol
        self.meta["nrow"] = self._nrow

    def _resolve_column_headers(self):
        """_summary_."""
        _cols = self.columns
        dup = self.meta["dup_cols"]
        if dup is None:
            dup = []
        # Solve duplicate values first
        count = dict(zip(dup, [0] * len(dup)))
        for idx, item in enumerate(_cols):
            if item in dup:
                _cols[idx] += f"_{count[item]}"
                count[item] += 1

        # Solve unnamed column headers
        _cols = [_col if _col else f"Unnamed_{_i+1}" for _i, _col in enumerate(_cols)]
        self.columns = _cols

    def read(
        self,
        lazy: bool = False,
    ):
        """_summary_."""
        if lazy:
            return TableLazy(
                data=self.data,
                index=self.index,
                columns=self.columns,
                **self.meta,
            )

        return Table(
            data=self.data,
            index=self.index,
            columns=self.columns,
            **self.meta,
        )


## Structs
class Grid(
    _BaseIO,
    _BaseStruct,
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
        _BaseIO.__init__(self, mode=mode)

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
        _BaseIO.close(self)
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

    @_BaseIO._check_mode
    def _write(
        self,
        data: array,
    ):
        """_summary_.

        Parameters
        ----------
        data : array
            _description_
        """
        raise NotImplementedError(NOT_IMPLEMENTED)

    @_BaseIO._check_mode
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


class GeomSource(_BaseIO, _BaseStruct):
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
    ):
        """_summary_."""
        obj = object.__new__(cls)

        return obj

    def __init__(
        self,
        file: str,
        mode: str = "r",
        overwrite: bool = False,
    ):
        _BaseStruct.__init__(self)
        _BaseIO.__init__(self, file, mode)

        if mode == "r":
            _map = GEOM_READ_DRIVER_MAP
        else:
            _map = GEOM_WRITE_DRIVER_MAP

        if self.path.suffix not in _map:
            raise DriverNotFoundError(gog="Geometry", path=self.path)

        driver = _map[self.path.suffix]

        self._driver = ogr.GetDriverByName(driver)
        info = gdal.VSIStatL(self.path.as_posix())

        if (self.path.exists() or info is not None) and not overwrite:
            self.src = self._driver.Open(self.path.as_posix(), self._mode)
        else:
            if not self._mode:
                raise OSError(f"Cannot create {self.path} in 'read' mode.")
            self.create(self.path)

        info = None
        self._count = 0
        self._cur_index = 0

        self.layer = self.src.GetLayer()
        if self.layer is not None:
            self._count = self.layer.GetFeatureCount()
            self._retrieve_columns()

    def __iter__(self):
        self.layer.ResetReading()
        self._cur_index = 0
        return self

    def __next__(self):
        if self._cur_index < self._count:
            r = self.layer.GetNextFeature()
            self._cur_index += 1
            return r
        else:
            raise StopIteration

    def __getitem__(self, fid):
        return self.layer.GetFeature(fid)

    def __reduce__(self):
        return self.__class__, (
            self.path,
            self._mode_str,
        )

    def _retrieve_columns(self):
        """Get the column headers from the swig object."""
        # Reset the columns to an empty dict
        self._columns = {}

        # Loop through the fields
        for idx, n in enumerate(self.fields):
            self._columns[n] = idx

    def close(self):
        """Close the GeomSouce."""
        _BaseIO.close(self)

        self.layer = None
        self.src = None
        self._driver = None

        gc.collect()

    # @property
    # def count(self):
    #     return self.layer.GetFeatureCount()

    def flush(self):
        """Flush the data.

        This only serves a purpose in write mode (`mode = 'w'`).
        """
        if self.src is not None:
            self.src.FlushCache()

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

        Yields
        ------
        ogr.Feature
            Features from the vector layer.
        """
        _c = 1
        for ft in self.layer:
            if si <= _c <= ei:
                yield ft
            _c += 1

    def reopen(
        self,
        mode: str = "r",
    ):
        """Reopen a closed GeomSource."""
        if not self._closed:
            return self
        obj = GeomSource.__new__(GeomSource, self.path, mode=mode)
        obj.__init__(self.path, mode=mode)
        return obj

    @property
    @_BaseIO._check_state
    def bounds(self):
        """Return the bounds of the GridSource.

        Returns
        -------
        list
            Contains the four boundaries of the grid. This take the form of \
[left, right, top, bottom]
        """
        return self.layer.GetExtent()

    @property
    @_BaseIO._check_state
    def columns(self):
        """Return the columns header of the attribute tabel.

        (Same as field, but determined from internal _columns attribute)

        Returns
        -------
        tuple
            Attribute table headers
        """
        return tuple(self._columns.keys())

    @property
    @_BaseIO._check_state
    def dtypes(self):
        """_summary_."""
        if self.layer is not None:
            _flds = self.layer.GetLayerDefn()
            dt = [_flds.GetFieldDefn(_i).type for _i in range(_flds.GetFieldCount())]
            _flds = None
            return dt

    @property
    @_BaseIO._check_state
    def fields(self):
        """Return the names of the fields."""
        if self.layer is not None:
            _flds = self.layer.GetLayerDefn()
            fh = [
                _flds.GetFieldDefn(_i).GetName() for _i in range(_flds.GetFieldCount())
            ]
            _flds = None
            return fh

    @property
    @_BaseIO._check_state
    def geom_type(self):
        """Return the geometry type."""
        return self.layer.GetGeomType()

    @property
    @_BaseIO._check_state
    def size(
        self,
    ):
        """Return the size (geometry count)."""
        if self.layer is not None:
            count = self.layer.GetFeatureCount()
            self._count = count
        return self._count

    @_BaseIO._check_mode
    @_BaseIO._check_state
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
        self.layer.CreateFeature(ft)

    @_BaseIO._check_mode
    @_BaseIO._check_state
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
        ft = ogr.Feature(self.layer.GetLayerDefn())
        ft.SetFrom(in_ft)

        for key, item in fmap:
            ft.SetField(key, item)

        self.layer.CreateFeature(ft)
        ft = None

    @_BaseIO._check_mode
    @_BaseIO._check_state
    def add_feature_from_defn(
        self,
        geom: ogr.Geometry,
        in_ft: ogr.Feature,
        out_ft: ogr.Feature,
    ):
        """Add a feature to a layer by using properties from another.

        Only in write (`'w'`) mode.

        Parameters
        ----------
        geom : ogr.Geometry
            The geometry of the new feature. Defined by OGR.
        in_ft : ogr.Feature
            The input feature. The properties and fieldinfo are used from this one
            to set information on the new feature. Defined by OGR.
        out_ft : ogr.Feature
            New feature. Empty. Defined by OGR.
        """
        out_ft.SetGeometry(geom)

        for n in range(in_ft.GetFieldCount()):
            out_ft.SetField(in_ft.GetFieldDefnRef(n).GetName(), in_ft.GetField(n))

        self.layer.CreateFeature(out_ft)

    @_BaseIO._check_mode
    @_BaseIO._check_state
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
        self.src = self._driver.CreateDataSource(path.as_posix())

    @_BaseIO._check_mode
    @_BaseIO._check_state
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
        self.layer.CreateField(
            ogr.FieldDefn(
                name,
                type,
            )
        )
        self._retrieve_columns()

    @_BaseIO._check_mode
    @_BaseIO._check_state
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
        self.layer.CreateFields(
            [ogr.FieldDefn(key, item) for key, item in fmap.items()]
        )
        self._retrieve_columns()

    @_BaseIO._check_mode
    @_BaseIO._check_state
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
        self.layer = self.src.CreateLayer(self.path.stem, srs, geom_type)

    @_BaseIO._check_mode
    @_BaseIO._check_state
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

        self.layer = self.src.CopyLayer(
            layer, self.path.stem, [f"OVERWRITE={_ow[overwrite]}"]
        )

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
        self.layer = self.src.CopyLayer(layer, layer_fn, ["OVERWRITE=YES"])

    def _get_layer(self, l_id):
        """_summary_."""
        raise NotImplementedError(NOT_IMPLEMENTED)

    @_BaseIO._check_state
    def get_srs(self):
        """Return the srs (Spatial Reference System)."""
        return self.layer.GetSpatialRef()

    @_BaseIO._check_mode
    @_BaseIO._check_state
    def set_layer_from_defn(
        self,
        ref: ogr.FeatureDefn,
    ):
        """Set layer meta from another layer's meta.

        Only in write (`'w'`) mode.

        Parameters
        ----------
        ref : ogr.FeatureDefn
            The definition of a layer. Defined by OGR.
        """
        for n in range(ref.GetFieldCount()):
            self.layer.CreateField(ref.GetFieldDefn(n))


class GridSource(_BaseIO, _BaseStruct):
    """A source object for geospatial gridded data.

    Essentially a gdal Dataset wrapper.

    Parameters
    ----------
    file : str
        The path to a file.
    chunk : tuple, optional
        Chunking size of the data.
    subset : str, optional
        The wanted subset of data. This is applicable to netCDF files containing \
multiple variables.
    var_as_band : bool, optional
        Whether to interpret the variables as bands.
        This is applicable to netCDF files containing multiple variables.
    mode : str, optional
        The I/O mode. Either `r` for reading or `w` for writing.

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
        chunk: tuple = None,
        subset: str = None,
        var_as_band: bool = False,
        mode: str = "r",
    ):
        """_summary_."""
        obj = object.__new__(cls)

        return obj

    def __init__(
        self,
        file: str,
        chunk: tuple = None,
        subset: str = None,
        var_as_band: bool = False,
        mode: str = "r",
    ):
        _open_options = []

        _BaseStruct.__init__(self)
        self._update_kwargs(
            subset=subset,
            var_as_band=var_as_band,
        )

        _BaseIO.__init__(self, file, mode)

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

        if not self._mode:
            self.src = gdal.OpenEx(self._path.as_posix(), open_options=_open_options)
            self._count = self.src.RasterCount

            if chunk is None:
                self._chunk = self.shape
            elif len(chunk) == 2:
                self._chunk = chunk
            else:
                raise ValueError(f"Incorrect chunking set: {chunk}")

            if self._count == 0:
                self.subset_dict = _read_gridsrouce_layers(
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
            mode=self._mode_str,
        )

    def __reduce__(self):
        return self.__class__, (
            self.path,
            self.chunk,
            self.subset,
            self._var_as_band,
            self._mode_str,
        )

    def close(self):
        """Close the GridSource."""
        _BaseIO.close(self)

        self.src = None
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
            self.path,
            self.chunk,
            self.subset,
            self._var_as_band,
        )
        obj.__init__(self.path, self._chunk, self.subset, self._var_as_band)
        return obj

    @property
    @_BaseIO._check_state
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
    @_BaseIO._check_state
    def dtype(self):
        """Return the data types of the field data."""
        if not self._dtype:
            _b = self[1]
            self._dtype = _b.dtype
            del _b
        return self._dtype

    @property
    @_BaseIO._check_state
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
    @_BaseIO._check_state
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
    @_BaseIO._check_state
    def size(self):
        """Return the number of bands."""
        count = self.src.RasterCount
        self._count = count
        return self._count

    @_BaseIO._check_mode
    @_BaseIO._check_state
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

    @_BaseIO._check_mode
    @_BaseIO._check_state
    def create_band(
        self,
    ):
        """Create a new band.

        Only in write (`'w'`) mode.

        This will append the numbers of bands.
        """
        self.src.AddBand()
        self._count += 1

    @_BaseIO._check_state
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

    @_BaseIO._check_state
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

    @_BaseIO._check_state
    def get_geotransform(self):
        """Return the geo transform of the grid."""
        return self.src.GetGeoTransform()

    @_BaseIO._check_state
    def get_srs(self):
        """Return the srs (Spatial Reference System) of the grid."""
        return self.src.GetSpatialRef()

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

    @_BaseIO._check_mode
    def set_geotransform(self, affine: tuple):
        """Set the geo transform of the grid.

        Parameters
        ----------
        affine : tuple
            An affine matrix.
        """
        self.src.SetGeoTransform(affine)

    @_BaseIO._check_mode
    @_BaseIO._check_state
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

    @_BaseIO._check_mode
    @_BaseIO._check_state
    def _write_array(
        self,
        array: "array",
        band: int,
    ):
        """_summary_."""
        raise NotImplementedError(NOT_IMPLEMENTED)


class _Table(_BaseStruct, metaclass=ABCMeta):
    def __init__(
        self,
        index: tuple = None,
        columns: tuple = None,
        **kwargs,
    ) -> object:
        """_summary_."""
        # Declarations
        self.dtypes = ()
        self.meta = kwargs
        self.index_col = -1

        if "index_col" in self.meta:
            self.index_col = self.meta["index_col"]

        index_int = list(range(kwargs["nrow"]))

        if "index_int" in kwargs:
            index_int = kwargs.pop("index_int")

        if "delimiter" in kwargs:
            self.delimiter = kwargs.pop("delimiter")

        # Create body of struct
        if "dtypes" in kwargs:
            self.dtypes = kwargs.pop("dtypes")

        if columns is None:
            columns = [f"col_{num}" for num in range(kwargs["ncol"])]

        # Some checking in regards to duplicates in column headers
        self.columns_raw = columns

        # Create the column indexing
        self._columns = dict(zip(columns, range(kwargs["ncol"])))

        if index is None:
            index = tuple(range(kwargs["nrow"]))
        self._index = dict(zip(index, index_int))

    def __del__(self):
        pass

    def __len__(self):
        return self.meta["nrow"]

    @abstractmethod
    def __getitem__(self, key):
        raise NotImplementedError(DD_NEED_IMPLEMENTED)

    # @abstractmethod
    # def __iter__(self):
    #     pass

    # @abstractmethod
    # def __next__(self):
    #     pass

    @property
    def columns(self):
        return tuple(self._columns.keys())

    @property
    def index(self):
        return tuple(self._index.keys())

    @property
    def shape(self):
        return (
            self.meta["nrow"],
            self.meta["ncol"],
        )


class Table(_Table):
    """Create a struct based on tabular data in a file.

    Parameters
    ----------
    data : BufferHandler | dict
        A datastream or a dictionary.
        The datastream is a connection through which data can pass.
    index : str | tuple, optional
        The index column from which the values are taken and used to index the rows.
    columns : list, optional
        The column headers of the table.
        If not supplied, it will be inferred from the file.

    Returns
    -------
    object
        An object containing actively loaded tabular data.
    """

    def __init__(
        self,
        data: BufferHandler | dict,
        index: str | tuple = None,
        columns: list = None,
        **kwargs,
    ) -> object:
        if isinstance(data, BufferHandler):
            self._build_from_stream(
                data,
                columns,
                kwargs,
            )

        elif isinstance(data, ndarray):
            self.data = data

        elif isinstance(data, list):
            self._build_from_list(data)

        _Table.__init__(
            self,
            index,
            columns,
            **kwargs,
        )

    def __iter__(self):
        raise NotImplementedError(DD_NOT_IMPLEMENTED)

    def __next__(self):
        raise NotImplementedError(DD_NOT_IMPLEMENTED)

    def __getitem__(self, keys):
        """_summary_."""
        keys = list(keys)

        if keys[0] != slice(None):
            keys[0] = self._index[keys[0]]

        if keys[1] != slice(None):
            keys[1] = self._columns[keys[1]]

        return self.data[keys[0], keys[1]]

    def __setitem__(self, key, value):
        self.data[key] = value

    def __eq__(self, other):
        return NotImplemented

    def __str__(self):
        if len(self.columns) > 6:
            return self._small_repr()
        else:
            return self._big_repr()

    def _big_repr(self):
        repr = ""
        repr += ", ".join([f"{item:6s}" for item in self.columns]) + "\n"
        m = zip(*[row[0:3] for row in self.data])
        for item in m:
            repr += ", ".join([f"{str(val):6s}" for val in item]) + "\n"
        repr += f"{'...':6s}, ...\n"
        return repr

    def _small_repr(self):
        repr = ""
        return repr

    def _build_from_stream(
        self,
        data: BufferHandler,
        columns: list,
        kwargs,
    ):
        """_summary_."""
        dtypes = kwargs["dtypes"]
        ncol = kwargs["ncol"]
        index_col = kwargs["index_col"]
        _pat_multi = regex_pattern(
            kwargs["delimiter"],
            multi=True,
        )
        with data as h:
            _d = _pat_multi.split(h.read().strip())

        _f = []
        cols = list(range(ncol))

        if kwargs["index_name"] is not None:
            columns.remove(kwargs["index_name"])
            kwargs["ncol"] -= 1

        if index_col >= 0 and index_col in cols:
            cols.remove(index_col)

        for c in cols:
            _f.append([dtypes[c](item) for item in replace_empty(_d[c::ncol])])

        self.data = column_stack((*_f,))

    def _build_from_dict(
        self,
        data: dict,
    ):
        """_summary_."""
        raise NotImplementedError(NOT_IMPLEMENTED)

    def _build_from_list(
        self,
        data: list,
    ):
        """_summary_."""
        self.data = array(data, dtype=object)

    def mean(self):
        """_summary_."""
        raise NotImplementedError(NOT_IMPLEMENTED)

    def max(self):
        """_summary_."""
        raise NotImplementedError(NOT_IMPLEMENTED)

    def upscale(
        self,
        delta: float,
        inplace: bool = False,
    ):
        """_summary_.

        Parameters
        ----------
        delta : float
            _description_
        inplace : bool, optional
            _description_, by default True

        """
        meta = self.meta.copy()

        _rnd = abs(floor(log10(delta)))

        _x = tuple(
            arange(min(self.index), max(self.index) + delta / 2, delta)
            .round(_rnd)
            .tolist()
        )

        _x = list(set(_x + self.index))
        _x.sort()

        _f = []

        for c in self.columns:
            _f.append(interp(_x, self.index, self[:, c]).tolist())

        data = column_stack(_f)

        meta.update(
            {
                "ncol": self.meta["ncol"],
                "nrow": len(data),
            }
        )

        if inplace:
            self.__init__(
                data=data,
                index=_x,
                columns=self.columns,
                **meta,
            )
            return None

        return Table(
            data=data,
            index=_x,
            columns=list(self.columns),
            **meta,
        )


class TableLazy(_Table):
    """A lazy read of tabular data in a file.

    Requires a datastream as input.

    Parameters
    ----------
    data : BufferHandler
        A stream.
    index : str | tuple, optional
        The index column used as row indices.
    columns : list, optional
        The column headers of the table.

    Returns
    -------
    object
        An object containing a connection via a stream to a file.
    """

    def __init__(
        self,
        data: BufferHandler,
        index: str | tuple = None,
        columns: list = None,
        **kwargs,
    ) -> object:
        self.data = data

        # Get internal indexing
        index_int = [None] * kwargs["nrow"]
        _c = 0

        with self.data as h:
            while True:
                index_int[_c] = h.tell()
                _c += 1
                if not h.readline() or _c == kwargs["nrow"]:
                    break

        kwargs["index_int"] = index_int
        del index_int

        _Table.__init__(
            self,
            index,
            columns,
            **kwargs,
        )

    def __iter__(self):
        raise NotImplementedError(DD_NOT_IMPLEMENTED)

    def __next__(self):
        raise NotImplementedError(DD_NOT_IMPLEMENTED)

    def __getitem__(
        self,
        oid: object,
    ):
        """_summary_."""
        try:
            idx = self._index[oid]
        except Exception:
            return None

        self.data.stream.seek(idx)

        return self.data.stream.readline().strip()

    def _build_lazy(self):
        raise NotImplementedError(NOT_IMPLEMENTED)

    def get(
        self,
        oid: str,
    ):
        """Get a row from the table based on the index.

        Parameters
        ----------
        oid : str
            Row identifier.
        """
        return self.__getitem__(oid)

    def set_index(
        self,
        key: str,
    ):
        """Set the index of the table.

        Parameters
        ----------
        key : str
            Column header.
            View available headers via <object>.columns.
        """
        if key not in self.headers:
            raise ValueError("")

        if key == self.index_col:
            return

        _pat_multi = regex_pattern(self.delim, multi=True)
        idx = self.header_index[key]
        new_index = [None] * self.handler.size

        with self.handler as h:
            c = 0

            for _nlines, sd in _text_chunk_gen(h, _pat_multi):
                new_index[c:_nlines] = [
                    *map(
                        self.dtypes[idx],
                        [item.decode() for item in sd[idx :: self._ncol]],
                    )
                ]
                c += _nlines
            del sd
        self.data = dict(zip(new_index, self.data.values()))


## I/O mutating methods
def merge_geom_layers(
    out_fn: Path | str,
    in_fn: Path | str,
    driver: str = None,
    append: bool = True,
    overwrite: bool = False,
    single_layer: bool = False,
    out_layer_name: str = None,
):
    """Merge multiple vector layers into one file.

    Either in one layer or multiple within the new file.
    Also usefull for appending datasets.

    Essentially a python friendly function of the ogr2ogr merge functionality.

    Parameters
    ----------
    out_fn : Path | str
        The resulting file name/ path.
    in_fn : Path | str
        The input file(s).
    driver : str, optional
        The driver to be used for the resulting file.
    append : bool, optional
        Whether to append an existing file.
    overwrite : bool, optional
        Whether to overwrite the resulting dataset.
    single_layer : bool, optional
        Output in a single layer.
    out_layer_name : str, optional
        The name of the resulting single layer.
    """
    # Create pathlib.Path objects
    out_fn = Path(out_fn)
    in_fn = Path(in_fn)

    # Sort the arguments
    args = []
    if not append and driver is not None:
        args += ["-f", driver]
    if append:
        args += ["-append"]
    if overwrite:
        args += ["-overwrite_ds"]
    if single_layer:
        args += ["-single"]
    args += ["-o", str(out_fn)]
    if out_layer_name is not None:
        args += ["-nln", out_layer_name]
    if "vsimem" in str(in_fn):
        in_fn = in_fn.as_posix()
    args += [str(in_fn)]

    # Execute the merging
    ogr_merge([*args])


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
    _handler = BufferHandler(file)

    parser = CSVParser(
        _handler,
        delimiter,
        header,
        index,
    )

    return parser.read(
        lazy=lazy,
    )


def open_geom(
    file: Path | str,
    mode: str = "r",
    overwrite: bool = False,
):
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

    Returns
    -------
    GeomSource
        Object that holds a connection to the source file.
    """
    return GeomSource(
        file,
        mode,
        overwrite,
    )


def open_grid(
    file: Path | str,
    chunk: tuple = None,
    subset: str = None,
    var_as_band: bool = False,
    mode: str = "r",
):
    """Open a grid source file.

    This source file is lazily read.

    Parameters
    ----------
    file : Path | str
        Path to the file.
    chunk : tuple, optional
        Chunk size in x and y direction.
    subset : str, optional
        In netCDF files, multiple variables are seen as subsets and can therefore not
        be loaded like normal bands. Specify one if one of those it wanted.
    var_as_band : bool, optional
        Again with netCDF files: if all variables have the same dimensions, set this
        flag to `True` to look the subsets as bands.
    mode : str, optional
        Open in `read` or `write` mode.

    Returns
    -------
    GridSource
        Object that holds a connection to the source file.
    """
    return GridSource(
        file,
        chunk,
        subset,
        var_as_band,
        mode,
    )
