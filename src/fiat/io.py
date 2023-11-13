"""Where I/O stuff gets handled."""

import atexit
import gc
import os
import weakref
from abc import ABCMeta, abstractmethod
from io import BufferedReader, BufferedWriter, FileIO, TextIOWrapper
from math import floor, log10
from typing import Any

from numpy import arange, array, column_stack, interp, ndarray
from osgeo import gdal, ogr, osr

from fiat.error import DriverNotFoundError
from fiat.util import (
    GEOM_DRIVER_MAP,
    GRID_DRIVER_MAP,
    Path,
    _dtypes_from_string,
    _dtypes_reversed,
    _read_gridsrouce_layers,
    _text_chunk_gen,
    deter_type,
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
        pass


class _BaseHandler(metaclass=ABCMeta):
    def __init__(
        self,
        file: str,
        skip: int = 0,
    ) -> "_BaseHandler":
        """_summary_."""
        self.path = Path(file)

        self.skip = skip
        self.size = self.read().count(os.linesep.encode())

        self.seek(self.skip)

    def __del__(self):
        self.flush()
        self.close()

    @abstractmethod
    def __repr__(self):
        pass

    def __enter__(self):
        return super().__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.flush()
        self.seek(self.skip)
        return False

    def read_line_once(self):
        """_summary_."""
        line = self.readline()
        self._skip += len(line)
        self.flush()
        return line


class _BaseStruct(metaclass=ABCMeta):
    """A struct container."""

    def __init__(self):
        self._kwargs = {}

    @abstractmethod
    def __del__(self):
        pass

    def __repr__(self):
        _mem_loc = f"{id(self):#018x}".upper()
        return f"<{self.__class__.__name__} object at {_mem_loc}>"

    def update_kwargs(
        self,
        **kwargs,
    ):
        """_summary_."""
        self._kwargs.update(
            **kwargs,
        )


## Handlers
class BufferHandler(_BaseHandler, BufferedReader):
    """_summary_."""

    def __init__(
        self,
        file: str,
        skip: int = 0,
    ) -> "BufferHandler":
        """_summary_.

        Parameters
        ----------
        file : str
            _description_

        Returns
        -------
        BufferHandler
            _description_
        """
        BufferedReader.__init__(self, FileIO(file))
        _BaseHandler.__init__(self, file, skip)

    def __repr__(self):
        return f"<{self.__class__.__name__} file='{self.path}' encoding=''>"

    def __reduce__(self):
        return self.__class__, (self.path, self.skip)


class BufferTextHandler(BufferedWriter):
    """_summary_."""

    def __init__(
        self,
        file: str,
        buffer_size: int = 100000,
        mode: str = "wb",
    ):
        self._file_stream = FileIO(file, mode=mode)
        self.path = file
        self._b_size = buffer_size

        BufferedWriter.__init__(
            self,
            self._file_stream,
            buffer_size=buffer_size,
        )

    def __del__(self):
        self.flush()
        self.close()
        self._file_stream.close()

    def __repr__(self):
        return f"<{self.__class__.__name__} file='{self.path}'>"

    def __reduce__(self):
        return self.__class__, (self.path, self._b_size, self.mode)


class GeomMemFileHandler:
    """_summary_."""

    def __init__(
        self,
        file: str or Path,
        srs: osr.SpatialReference,
        layer_meta: ogr.FeatureDefn,
    ):
        """_summary_.

        Parameters
        ----------
        file : strorPath
            _description_
        srs : osr.SpatialReference
            _description_
        layer_meta : ogr.FeatureDefn
            _description_
        field_meta : dict
            _description_
        """
        self._memory = open_geom("memset", "w")
        self._memory.create_layer(
            srs,
            layer_meta.GetGeomType(),
        )
        self._memory.set_layer_from_defn(
            layer_meta,
        )

        self._drive = open_geom(file, "w")

    def __del__(self):
        self._clear_cache()
        self._memory = None
        self._drive = None

    def __reduce__(self) -> str | tuple[Any, ...]:
        pass

    def _clear_cache(self):
        self._memory.src.DeleteLayer("memset")

    def add_feature(
        self,
        ft: ogr.Feature,
        fmap: dict,
    ):
        """_summary_."""
        _local_ft = ogr.Feature(self._memory.layer.GetLayerDefn())
        _local_ft.SetFID(ft.GetFID())
        _local_ft.SetGeometry(ft.GetGeometryRef())
        for num in range(ft.GetFieldCount()):
            _local_ft.SetField(
                num,
                ft.GetField(num),
            )

        for key, item in fmap.items():
            _local_ft.SetField(
                key,
                item,
            )

        self._memory.layer.CreateFeature(_local_ft)
        _local_ft = None

    def create_fields(
        self,
        flds: zip,
    ):
        """_summary_."""
        self._memory.create_fields(
            dict(flds),
        )

    def dump2drive(self):
        """_summary_."""
        self._drive.create_layer_from_copy(self._memory.layer)
        self._drive.flush()

    # def set_fields(
    #     self,
    #     fid: int,
    #     fmap: dict,
    # ):
    #     """_summary_"""

    #     _local_ft = self._memory[fid]
    #     for key, item in fmap.items():
    #         _local_ft.SetField(
    #             key,
    #             item,
    #         )

    #     self._memory.layer.UpdateFeature(_local_ft)
    #     _local_ft = None


class TextHandler(_BaseHandler, TextIOWrapper):
    """_summary_."""

    def __init__(
        self,
        file: str,
    ) -> "TextHandler":
        """_summary_.

        Parameters
        ----------
        file : str
            _description_

        Returns
        -------
        TextHandler
            _description_
        """
        TextIOWrapper.__init__(self, FileIO(file))
        _BaseHandler.__init__()

    def __repr__(self):
        return f"<{self.__class__.__name__} file='{self.path}'>"


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
        self.data.seek(0)

        while True:
            self._nrow -= 1
            cur_pos = self.data.tell()
            line = self.data.readline().decode("utf-8-sig")

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
                self.data.seek(cur_pos)
                self._nrow += 1
                break

            self.columns = [item.strip() for item in line.split(self.delim)]
            self._resolve_column_headers()
            self._ncol = len(self.columns)
            break

        self.data.skip = self.data.tell()
        self.meta["ncol"] = self._ncol
        self.meta["nrow"] = self._nrow

    def _resolve_column_headers(self):
        """_summary_."""
        _cols = self.columns
        _cols = [_col if _col else f"Unnamed_{_i+1}" for _i, _col in enumerate(_cols)]
        self.columns = _cols

    def read(
        self,
        large: bool = False,
    ):
        """_summary_."""
        if large:
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

    def read_exp(self):
        """_summary_."""
        return ExposureTable(
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
    """_summary_."""

    def __init__(
        self,
        band: gdal.Band,
        chunk: tuple = None,
        mode: str = "r",
    ):
        """_summary_."""
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
            ValueError("")

    def __iter__(self):
        self.flush()
        self._reset_chunking()
        return self

    def __next__(self):
        if self._u > self._y:
            self.flush()
            raise StopIteration

        w = min(self._chunk[0], self._x - self._l)
        h = min(self._chunk[1], self._y - self._u)

        window = (
            self._l,
            self._u,
            w,
            h,
        )
        chunk = self[window]

        self._l += self._chunk[0]
        if self._l > self._x:
            self._l = 0
            self._u += self._chunk[1]

        return window, chunk

        # for l, u in self._windows:
        #     s = time.time()

        #     if self._last_chunk is not None:
        #         self._last_chunk = None

        #     w = min(self._chunk[0], self._x - l)
        #     h = min(self._chunk[1], self._y - u)

        #     chunk = self[l, u, w, h]
        #     self._last_chunk = chunk

        #     e = time.time() - s
        #     print(f"{e} seconds! (iter)")

        # return (l, u, w, h), chunk

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
        """_summary_."""
        _BaseIO.close(self)
        self.src = None
        gc.collect()

    def flush(self):
        """_summary_."""
        if self.src is not None:
            self.src.FlushCache()

    @property
    def chunk(self):
        """_summary_."""
        return self._chunk

    @property
    def shape(self):
        """_summary_."""
        return self._x, self._y

    def get_metadata_item(
        self,
        entry: str,
    ):
        """_summary_."""
        return self.src.GetMetadataItem(entry)

    def set_chunk_size(
        self,
        chunk: tuple,
    ):
        """_summary_."""
        self._chunk = chunk

    @_BaseIO._check_mode
    def write(
        self,
        data: array,
    ):
        """_summary_.

        Parameters
        ----------
        data : array
            _description_
        """
        pass

    @_BaseIO._check_mode
    def write_chunk(
        self,
        chunk: array,
        upper_left: tuple | list,
    ):
        """_summary_.

        Parameters
        ----------
        chunk : array
            _description_
        """
        self.src.WriteArray(chunk, *upper_left)


class GeomSource(_BaseIO, _BaseStruct):
    """_summary_."""

    _type_map = {
        "int": ogr.OFTInteger64,
        "float": ogr.OFTReal,
        "str": ogr.OFTString,
    }

    def __new__(
        cls,
        file: str,
        mode: str = "r",
    ):
        """_summary_."""
        obj = object.__new__(cls)

        return obj

    def __init__(
        self,
        file: str,
        mode: str = "r",
    ):
        """Essentially an OGR DataSource Wrapper.

        Parameters
        ----------
        file : str
            _description_
        driver : str, optional
            _description_, by default ""
        mode : str, optional
            _description_, by default "r"

        Returns
        -------
        object
            _description_

        Raises
        ------
        ValueError
            _description_
        DriverNotFoundError
            _description_
        OSError
            _description_
        OSError
            _description_
        """
        _BaseIO.__init__(self, file, mode)

        if self.path.suffix not in GEOM_DRIVER_MAP:
            raise DriverNotFoundError("")

        driver = GEOM_DRIVER_MAP[self.path.suffix]

        self._driver = ogr.GetDriverByName(driver)

        if self.path.exists():
            self.src = self._driver.Open(str(self.path), self._mode)
        else:
            if not self._mode:
                raise OSError("")
            self.src = self._driver.CreateDataSource(str(self.path))

        self.count = 0
        self._cur_index = 0

        self.layer = self.src.GetLayer()
        if self.layer is not None:
            self.count = self.layer.GetFeatureCount()

    def __iter__(self):
        self.layer.ResetReading()
        self._cur_index = 0
        return self

    def __next__(self):
        if self._cur_index < self.count:
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

    def close(self):
        """_summary_."""
        _BaseIO.close(self)

        self.layer = None
        self.src = None
        self._driver = None

        gc.collect()

    # @property
    # def count(self):
    #     return self.layer.GetFeatureCount()

    def flush(self):
        """_summary_."""
        if self.src is not None:
            self.src.FlushCache()

    def reopen(self):
        """_summary_."""
        if not self._closed:
            return self
        obj = GeomSource.__new__(GeomSource, self.path)
        obj.__init__(self.path)
        return obj

    @property
    @_BaseIO._check_state
    def bounds(self):
        """_summary_."""
        return self.layer.GetExtent()

    @property
    @_BaseIO._check_state
    def fields(self):
        """_summary_."""
        if self.layer is not None:
            _flds = self.layer.GetLayerDefn()
            fh = [
                _flds.GetFieldDefn(_i).GetName() for _i in range(_flds.GetFieldCount())
            ]
            _flds = None
            return fh

    @_BaseIO._check_mode
    @_BaseIO._check_state
    def add_feature(
        self,
        ft: ogr.Feature,
    ):
        """_summary_."""
        self.layer.CreateFeature(ft)

    @_BaseIO._check_mode
    @_BaseIO._check_state
    def add_feature_from_defn(
        self,
        geom: ogr.Geometry,
        in_ft: ogr.Feature,
        out_ft: ogr.Feature,
    ):
        """_summary_."""
        out_ft.SetGeometry(geom)

        for n in range(in_ft.GetFieldCount()):
            out_ft.SetField(in_ft.GetFieldDefnRef(n).GetName(), in_ft.GetField(n))

        self.layer.CreateFeature(out_ft)

    @_BaseIO._check_mode
    @_BaseIO._check_state
    def create_field(
        self,
        name: str,
        type: object,
    ):
        """_summary_.

        Parameters
        ----------
        name : str
            _description_
        type : _type_
            _description_
        """
        self.layer.CreateField(
            ogr.FieldDefn(
                name,
                GeomSource._type_map[type],
            )
        )

    @_BaseIO._check_mode
    @_BaseIO._check_state
    def create_fields(
        self,
        fmap: dict,
    ):
        """_summary_.

        Parameters
        ----------
        name : str
            _description_
        type : _type_
            _description_
        """
        self.layer.CreateFields(
            [
                ogr.FieldDefn(key, GeomSource._type_map[item])
                for key, item in fmap.items()
            ]
        )

    @_BaseIO._check_mode
    @_BaseIO._check_state
    def create_layer(
        self,
        srs: osr.SpatialReference,
        geom_type: int,
    ):
        """_summary_.

        Parameters
        ----------
        srs : osr.SpatialReference
            _description_
        """
        self.layer = self.src.CreateLayer(self.path.stem, srs, geom_type)

    @_BaseIO._check_mode
    @_BaseIO._check_state
    def create_layer_from_copy(
        self,
        layer: ogr.Layer,
        overwrite: bool = True,
    ):
        """_Summary_.

        Parameters
        ----------
        layer : ogr.Layer
            _description_
        """
        _ow = {
            True: "YES",
            False: "NO",
        }

        self.layer = self.src.CopyLayer(
            layer, self.path.stem, [f"OVERWRITE={_ow[overwrite]}"]
        )

    def get_bbox(self):
        """_summary_."""
        return self.layer.GetExtent()

    def get_layer(self, l_id):
        """_summary_."""
        pass

    @_BaseIO._check_state
    def get_srs(self):
        """_Summary_."""
        return self.layer.GetSpatialRef()

    @_BaseIO._check_mode
    @_BaseIO._check_state
    def set_layer_from_defn(
        self,
        ref: ogr.FeatureDefn,
    ):
        """_summary_.

        Parameters
        ----------
        ref : ogr.FeatureDefn
            _description_
        """
        for n in range(ref.GetFieldCount()):
            self.layer.CreateField(ref.GetFieldDefn(n))


class GridSource(_BaseIO, _BaseStruct):
    """_summary_."""

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
        """Essentially a GDAL Dataset Wrapper.

        Parameters
        ----------
        file : str
            _description_
        chunk : tuple, optional
            _description_, by default None
        subset : str, optional
            _description_, by default None
        var_as_band : bool, optional
            _description_, by default False
        mode : str, optional
            _description_, by default "r"

        Raises
        ------
        DriverNotFoundError
            _description_
        """
        _open_options = []

        _BaseStruct.__init__(self)
        self.update_kwargs(
            subset=subset,
            var_as_band=var_as_band,
        )

        _BaseIO.__init__(self, file, mode)

        if self.path.suffix not in GRID_DRIVER_MAP:
            raise DriverNotFoundError("")

        driver = GRID_DRIVER_MAP[self.path.suffix]

        if not subset:
            subset = None
        self.subset = subset

        if subset is not None and not var_as_band:
            self._path = f"{driver.upper()}:" + f'"{file}"' + f":{subset}"

        if var_as_band:
            _open_options.append("VARIABLES_AS_BANDS=YES")
        self._var_as_band = var_as_band

        self._driver = gdal.GetDriverByName(driver)

        self.src = None
        self._chunk = None
        self._dtype = None
        self.subset_dict = None
        self.count = 0
        self._cur_index = 1

        if not self._mode:
            self.src = gdal.OpenEx(str(self._path), open_options=_open_options)
            self.count = self.src.RasterCount

            if chunk is None:
                self._chunk = self.shape
            elif len(chunk) == 2:
                self._chunk = chunk
            else:
                ValueError("")

            if self.count == 0:
                self.subset_dict = _read_gridsrouce_layers(
                    self.src,
                )

    def __iter__(self):
        self._cur_index = 1
        return self

    def __next__(self):
        if self._cur_index < self.count + 1:
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
        """_summary_."""
        _BaseIO.close(self)

        self.src = None
        self._driver = None

        gc.collect()

    def flush(self):
        """_summary_."""
        if self.src is not None:
            self.src.FlushCache()

    def reopen(self):
        """_summary_."""
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
        """_summary_."""
        _gtf = self.src.GetGeoTransform()
        return (
            _gtf[0],
            _gtf[0] + _gtf[1] * self.src.RasterXSize,
            _gtf[3] + _gtf[5] * self.src.RasterYSize,
            _gtf[3],
        )

    @property
    def chunk(self):
        """_summary_."""
        return self._chunk

    @property
    @_BaseIO._check_state
    def dtype(self):
        """_summary_."""
        if not self._dtype:
            _b = self[1]
            self._dtype = _b.dtype
            del _b
        return self._dtype

    @property
    @_BaseIO._check_state
    def shape(self):
        """_summary_."""
        return (
            self.src.RasterXSize,
            self.src.RasterYSize,
        )

    @_BaseIO._check_mode
    @_BaseIO._check_state
    def create(
        self,
        shape: tuple,
        nb: int,
        type: int,
        options: list = [],
    ):
        """_summary_."""
        self.src = self._driver.Create(
            str(self.path),
            *shape,
            nb,
            type,
            options=options,
        )

        self.count = nb

    @_BaseIO._check_mode
    @_BaseIO._check_state
    def create_band(
        self,
    ):
        """_summary_."""
        self.src.AddBand()
        self.count += 1

    @_BaseIO._check_state
    def deter_band_names(
        self,
    ):
        """_summary_."""
        _names = []
        for n in range(self.count):
            name = self.get_band_name(n + 1)
            if not name:
                _names.append(f"Band{n+1}")
                continue
            _names.append(name)

        return _names

    @_BaseIO._check_state
    def get_band_name(self, n: int):
        """_summary_."""
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
        """_summary_."""
        _names = []
        for n in range(self.count):
            _names.append(self.get_band_name(n + 1))

        return _names

    @_BaseIO._check_state
    def get_bbox(self):
        """_summary_."""
        gtf = self.src.GetGeoTransform()
        bbox = (
            gtf[0],
            gtf[0] + gtf[1] * self.src.RasterXSize,
            gtf[3] + gtf[5] * self.src.RasterYSize,
            gtf[3],
        )
        gtf = None

        return bbox

    @_BaseIO._check_state
    def get_geotransform(self):
        """_summary_."""
        return self.src.GetGeoTransform()

    @_BaseIO._check_state
    def get_srs(self):
        """_summary_."""
        return self.src.GetSpatialRef()

    def set_chunk_size(
        self,
        chunk: tuple,
    ):
        """_summary_."""
        self._chunk = chunk

    @_BaseIO._check_mode
    def set_geotransform(self, affine: tuple):
        """_summary_."""
        self.src.SetGeoTransform(affine)

    @_BaseIO._check_mode
    @_BaseIO._check_state
    def set_srs(
        self,
        srs: osr.SpatialReference,
    ):
        """_summary_."""
        self.src.SetSpatialRef(srs)

    @_BaseIO._check_mode
    @_BaseIO._check_state
    def write_array(
        self,
        array: "array",
        band: int,
    ):
        """_summary_."""
        pass


class _Table(_BaseStruct, metaclass=ABCMeta):
    def __init__(
        self,
        index: tuple = None,
        columns: tuple = None,
        **kwargs,
    ) -> object:
        """_summary_."""
        # Declarations
        self._dup_cols = None
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
        if len(set(columns)) != len(columns):
            _set = list(set(columns))
            _counts = [columns.count(elem) for elem in _set]
            _dup = [elem for _i, elem in enumerate(_set) if _counts[_i] > 1]
            self._dup_cols = _dup

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
    def __getitem__(self):
        pass

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
    """_summary_."""

    def __init__(
        self,
        data: BufferHandler or dict,
        index: str or tuple = None,
        columns: list = None,
        **kwargs,
    ) -> object:
        """_summary_.

        Parameters
        ----------
        file : str
            _description_

        Returns
        -------
        object
            _description_
        """
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
        pass

    def __next__(self):
        pass

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

    def __eq__(self):
        pass

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
        pass

    def _build_from_list(
        self,
        data: list,
    ):
        """_summary_."""
        self.data = array(data, dtype=object)

    def mean():
        """_summary_."""
        pass

    def max():
        """_summary_."""
        pass

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
            arange(min(self.index), max(self.index) + delta / 2, delta).round(_rnd)
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
    """_summary_."""

    def __init__(
        self,
        data: BufferHandler,
        index: str or tuple = None,
        columns: list = None,
        **kwargs,
    ) -> object:
        """_summary_.

        Parameters
        ----------
        file : str
            _description_

        Returns
        -------
        object
            _description_
        """
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
        pass

    def __next__(self):
        pass

    def __getitem__(
        self,
        oid: object,
    ):
        """_summary_."""
        try:
            idx = self._index[oid]
        except Exception:
            return None

        self.data.seek(idx)

        return self.data.readline().strip()

    def _build_lazy(self):
        pass

    def get(
        self,
        oid: str,
    ):
        """_summary_."""
        return self.__getitem__(oid)

    def set_index(
        self,
        key: str,
    ):
        """_summary_."""
        if key not in self.headers:
            raise ValueError("")

        if key == self.index_col:
            return

        idx = self.header_index[key]
        new_index = [None] * self.handler.size

        with self.handler as h:
            c = 0

            for _nlines, sd in _text_chunk_gen(h):
                new_index[c:_nlines] = [
                    *map(
                        self.dtypes[idx],
                        [item.decode() for item in sd[idx :: self._ncol]],
                    )
                ]
                c += _nlines
            del sd
        self.data = dict(zip(new_index, self.data.values()))


class ExposureTable(TableLazy):
    """_summary_."""

    def __init__(
        self,
        data: BufferHandler,
        index: str or tuple = None,
        columns: list = None,
        **kwargs,
    ):
        """Create a table just for exposure data.

        Parameters
        ----------
        data : BufferHandler
            _description_
        index : strortuple, optional
            _description_, by default None
        columns : list, optional
            _description_, by default None
        """
        TableLazy.__init__(
            self,
            data,
            index,
            columns,
            **kwargs,
        )

        _dc_cols = ["Damage Function:", "Max Potential Damage"]

        for req in _dc_cols:
            req_s = req.strip(":").lower().replace(" ", "_")
            self.__setattr__(
                req_s,
                dict(
                    [
                        (item.split(":")[1].strip(), self._columns[item])
                        for item in self.columns
                        if item.startswith(req)
                    ]
                ),
            )

        self._blueprint_columns = (
            ["Inundation Depth", "Reduction Factor"]
            + [f"Damage: {item}" for item in self.damage_function.keys()]
            + ["Total Damage"]
        )

        self._dat_len = len(self._blueprint_columns)

    def create_specific_columns(self, name: str):
        """_summary_."""
        _out = []
        if name:
            name = f"({name})"
        for bp in self._blueprint_columns:
            # _parts = bp.split(":")

            # if len(_parts) == 1:
            #     bp += f" {name}"
            #     _out.append(bp)
            #     continue

            bp += f" {name}"
            _out.append(bp.strip())

        return _out

    def create_all_columns(
        self,
        names: list,
        extra: list = None,
    ):
        """_summary_."""
        cols = []
        for n in names:
            cols += self.create_specific_columns(n)

        if extra is not None:
            cols += extra

        return cols

    def gen_dat_dtypes(self):
        """_summary_."""
        return ",".join(["float"] * self._dat_len).encode()


## Open
def open_csv(
    file: str,
    delimiter: str = ",",
    header: bool = True,
    index: str = None,
    large: bool = False,
) -> object:
    """_summary_.

    Parameters
    ----------
    file : str
        _description_

    Returns
    -------
    object
        _description_
    """
    _handler = BufferHandler(file)

    parser = CSVParser(
        _handler,
        delimiter,
        header,
        index,
    )

    return parser.read(
        large=large,
    )


def open_exp(
    file: str,
    delimiter: str = ",",
    header: bool = True,
    index: str = None,
):
    """_summary_."""
    _handler = BufferHandler(file)

    parser = CSVParser(
        _handler,
        delimiter,
        header,
        index,
    )

    return parser.read_exp()


def open_geom(
    file: str,
    mode: str = "r",
):
    """_summary_."""
    return GeomSource(
        file,
        mode,
    )


def open_grid(
    file: str,
    chunk: tuple = None,
    subset: str = None,
    var_as_band: bool = False,
    mode: str = "r",
):
    """_summary_."""
    return GridSource(
        file,
        chunk,
        subset,
        var_as_band,
        mode,
    )
