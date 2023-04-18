import atexit
import gc
import os
import weakref
from abc import ABCMeta, abstractmethod
from io import BufferedReader, FileIO, TextIOWrapper
from math import floor, log10

import regex
from numpy import arange, cumsum, interp
from osgeo import gdal, ogr, osr

from delft_fiat.error import DriverNotFoundError
from delft_fiat.util import (
    Path,
    _dtypes_reversed,
    _GeomDriverTable,
    _GridDriverTable,
    _text_chunk_gen,
    deter_type,
    replace_empty,
)

_IOS = weakref.WeakValueDictionary()
_IOS_COUNT = 1


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

    def __init__(
        self,
        file: str,
        mode: str = "r",
    ):
        """_summary_"""

        if mode not in _BaseIO._mode_map:
            raise ValueError("")

        self.path = Path(file)

        self._closed = False
        self._mode = _BaseIO._mode_map[mode]

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
    ) -> "_BaseHandler":
        """_summary_"""

        self.path = Path(file)

        self.skip = 0
        self.size = sum(1 for _ in self)

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
        line = self.readline()
        self._skip += len(line)
        self.flush()
        return line


class _BaseStruct(metaclass=ABCMeta):
    """A struct container"""

    @abstractmethod
    def __del__(self):
        pass

    def __repr__(self):
        return f"<{self.__class__.__name__} object at {id(self):#018x}>"


## Handlers
class BufferHandler(_BaseHandler, BufferedReader):
    def __init__(self, file: str) -> "BufferHandler":
        """_summary_

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
        _BaseHandler.__init__(self, file)

    def __repr__(self):
        return f"<io.{self.__class__.__name__} file='{self.path}' encoding=''>"


class TextHandler(_BaseHandler, TextIOWrapper):
    def __init__(
        self,
        file: str,
    ) -> "TextHandler":
        """_summary_

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
        return f"<io.{self.__class__.__name__} file='{self.path}'>"


## Parsing
def _Parse_CSV(
    obj,
):
    """_summary_"""

    meta = {}
    _meta = {}
    hdrs = []

    obj.handler.seek(0)

    while True:
        cur_pos = obj.handler.tell()
        line = obj.handler.readline().decode("utf-8-sig")
        if line.startswith("#"):
            t = line.strip().split("=")
            if len(t) == 1:
                lst = t[0].split(",")
                _entry = lst[0].strip().replace("#", "").lower()
                _val = [item.strip() for item in lst[1:]]
                meta[_entry] = _val
                setattr(obj, _entry, tuple(_val))
            else:
                key, item = t
                meta[key.strip().replace("#", "").lower()] = item.strip()
            continue
        if not obj._header:
            _ncol = len(obj.re.split(line.encode("utf-8-sig")))
            hdrs = [f"col_{n}" for n in range(_ncol)]
            obj.handler.seek(cur_pos)
            break
        hdrs = [item.strip() for item in line.split(",")]
        break

    obj.handler.skip = obj.handler.tell()
    _ncol = len(hdrs)
    obj._ncol = _ncol

    if "dtypes" not in meta:
        _new = [0] * _ncol
        with obj.handler as _h:
            for _nlines, sd in _text_chunk_gen(_h, obj.re_m):
                for idx in range(_ncol):
                    _new[idx] = max(
                        deter_type(b"\n".join(sd[idx::_ncol]), _nlines),
                        _new[idx],
                    )

            del sd
            meta["dtypes"] = [_dtypes_reversed[n] for n in _new]
            setattr(obj, "dtypes", tuple(meta["dtypes"]))

    obj._meta = _meta
    obj.meta = meta
    obj.headers = hdrs


## Structs
class _CSV(_BaseStruct, metaclass=ABCMeta):
    def __init__(
        self,
        file: str,
        header: bool = True,
    ):
        """_summary_"""

        self._header = header
        self.re = regex.compile(rb'"[^"]*"(*SKIP)(*FAIL)|,')
        self.re_m = regex.compile(rb'"[^"]*"(*SKIP)(*FAIL)|,|\r\n')

        self.handler = BufferHandler(file)
        # Create body of struct
        _Parse_CSV(
            self,
        )

        self.index_col = self.headers[0]
        self.header_index = dict(zip(self.headers, range(len(self.headers))))

    def __del__(self):
        self.handler = None

    def __getitem__(self):
        pass

    def __iter__(self):
        pass


class CSVLarge(_CSV):
    def __init__(
        self,
        file: str,
        header: bool = True,
    ) -> object:
        """_summary_

        Parameters
        ----------
        file : str
            _description_

        Returns
        -------
        object
            _description_
        """

        _CSV.__init__(self, file, header)

        index = [None] * self.handler.size
        lines = [None] * self.handler.size
        lines[0] = self.handler.skip

        with self.handler as h:
            c = 0
            while True:
                line = h.readline().strip()
                if not line:
                    break
                z = self.re.split(line)[0]
                index[c] = self.dtypes[0](z.decode())
                lines[c + 1] = len(line) + 2
                c += 1

        self.data = dict(zip(index, cumsum(lines)))

        del lines
        del index

    def __iter__(self):
        pass

    def __next__(self):
        pass

    def __getitem__(
        self,
        oid: "ANY",
    ):
        """_summary_"""

        try:
            idx = self.data[oid]
        except Exception:
            return None
        self.handler.seek(idx)

        return replace_empty(self.re.split(self.handler.readline().strip()))

    def get(
        self,
        oid: str,
    ):
        """_summary_"""

        return self.__getitem__(oid)

    def set_index(
        self,
        key: str,
    ):
        """_summary_"""

        if key not in self.headers:
            raise ValueError("")

        if key == self.index_col:
            return

        idx = self.header_index[key]
        new_index = [None] * self.handler.size

        with self.handler as h:
            c = 0

            for _nlines, sd in _text_chunk_gen(h, self.re_m):
                new_index[c:_nlines] = [
                    *map(
                        self.dtypes[idx],
                        [item.decode() for item in sd[idx :: self._ncol]],
                    )
                ]
                c += _nlines
            del sd
        self.data = dict(zip(new_index, self.data.values()))


class CSVSmall(_CSV):
    def __init__(
        self,
        file: str,
        header: bool = True,
    ) -> object:
        """_summary_

        Parameters
        ----------
        file : str
            _description_

        Returns
        -------
        object
            _description_
        """

        _CSV.__init__(self, file, header)

        with self.handler as h:
            b = [replace_empty(self.re.split(line.strip())) for line in h.readlines()]

        self.handler = None

        self.data = dict(
            zip(
                self.headers,
                [tuple(map(x, y)) for x, y in zip(self.dtypes, zip(*b))],
            )
        )

    def __iter__(self):
        pass

    def next(self):
        pass

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value

    def __eq__(self):
        pass

    def __repr__(self):
        if len(self.headers) > 6:
            return self._small_repr()
        else:
            return self._big_repr()

    def _big_repr(self):
        repr = ""
        repr += ", ".join([f"{item:6s}" for item in self.headers]) + "\n"
        m = zip(*[row[0:3] for row in [*self.data.values()]])
        for item in m:
            repr += ", ".join([f"{str(val):6s}" for val in item]) + "\n"
        repr += f"{'...':6s}, ...\n"
        return repr

    def _small_repr(self):
        repr = ""

        char_len = [len(h) for h in self.headers]

        repr += ", ".join([f"{item:6s}" for item in self.headers[0:3]]) + " ... "
        repr += ", ".join([f"{item:6s}" for item in self.headers[-3:]]) + "\n"

        m = zip(*[row[0:4] for row in [*self.data.values()]])
        for item in m:
            repr += (
                ", ".join(
                    [f"{str(val):{l}s}" for val, l in zip(item[0:3], char_len[0:3])]
                )
                + " ... "
            )
            repr += (
                ", ".join(
                    [f"{str(val):{l}s}" for val, l in zip(item[-3:], char_len[-3:])]
                )
                + "\n"
            )

        repr += "...\n"
        return repr

    def mean():
        pass

    def max():
        pass

    def upscale(
        self,
        delta: float,
        inplace: bool = True,
    ):
        """_summary_

        Parameters
        ----------
        delta : float
            _description_
        inplace : bool, optional
            _description_, by default True

        """

        _rnd = abs(floor(log10(delta)))

        _x = tuple(
            arange(
                min(self[self.index_col]), max(self[self.index_col]) + delta, delta
            ).round(_rnd)
        )

        _hdrs = self.headers.copy()
        _hdrs.remove(self.index_col)

        for c in _hdrs:
            self[c] = tuple(interp(_x, self[self.index_col], self[c]))

        self[self.index_col] = _x
        return None


class GeomSource(_BaseIO, _BaseStruct):
    def __new__(
        cls,
        file: str,
        driver: str = "",
        mode: str = "r",
    ):
        """_summary_"""

        obj = object.__new__(cls)
        obj.__init__(file, driver, mode)

        return obj

    def __init__(
        self,
        file: str,
        driver: str = "",
        mode: str = "r",
    ) -> object:
        """Essentially an OGR DataSource Wrapper

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

        if not driver and not self._mode:
            driver = _GeomDriverTable[self.path.suffix]

        if driver not in _GeomDriverTable.values():
            raise DriverNotFoundError("")

        if _GeomDriverTable[self.path.suffix] != driver:
            raise OSError(
                f"Path suffix ({self.path.suffix}) does not match driver ({driver})"
            )

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

    def close(self):
        _BaseIO.close(self)

        self.layer = None
        self.src = None
        self._driver = None

        gc.collect()

    def flush(self):
        self.src.FlushCache()

    def reopen(self):
        """_summary_"""

        if not self._closed:
            return self
        return GeomSource.__new__(GeomSource, self.path)

    @_BaseIO._check_mode
    @_BaseIO._check_state
    def add_feature(
        self,
        ft: ogr.Feature,
    ):
        self.layer.CreateFeature(ft)

    @_BaseIO._check_mode
    @_BaseIO._check_state
    def add_feature_from_defn(
        self,
        geom: ogr.Geometry,
        in_ft: ogr.Feature,
        out_ft: ogr.Feature,
    ):
        out_ft.SetGeometry(geom)

        for n in range(in_ft.GetFieldCount()):
            out_ft.SetField(in_ft.GetFieldDefnRef(n).GetName(), in_ft.GetField(n))

        self.layer.CreateFeature(out_ft)

    @_BaseIO._check_mode
    @_BaseIO._check_state
    def create_layer(
        self,
        srs: osr.SpatialReference,
        geom_type: int,
    ):
        """_summary_

        Parameters
        ----------
        srs : osr.SpatialReference
            _description_
        """

        self.layer = self.src.CreateLayer(self.path.stem, srs, geom_type)

    @_BaseIO._check_mode
    @_BaseIO._check_state
    def create_layer_from_copy(self, layer: ogr.Layer):
        """_Summary_

        Parameters
        ----------
        layer : ogr.Layer
            _description_
        """

        self.layer = self.src.CopyLayer(layer, self.path.stem, ["OVERWRITE=YES"])

    def get_bbox(self):
        """_summary_"""

        return self.layer.GetExtent()

    def get_layer(self, l_id):
        pass

    @_BaseIO._check_state
    def get_srs(self):
        """_Summary_"""

        return self.layer.GetSpatialRef()

    @_BaseIO._check_mode
    @_BaseIO._check_state
    def set_field(
        self,
        name: str,
        ogr_type,
    ):
        pass

    @_BaseIO._check_mode
    @_BaseIO._check_state
    def set_layer_from_defn(
        self,
        ref: ogr.FeatureDefn,
    ):
        for n in range(ref.GetFieldCount()):
            self.layer.CreateField(ref.GetFieldDefn(n))


class GridSource(_BaseIO, _BaseStruct):
    _type_map = {
        "float": gdal.GFT_Real,
        "int": gdal.GDT_Int16,
        "string": gdal.GFT_String,
    }

    def __new__(
        cls,
        file: str,
        driver: str = "",
        mode: str = "r",
    ):
        """_summary_"""

        obj = object.__new__(cls)
        obj.__init__(file, driver, mode)

        return obj

    def __init__(
        self,
        file: str,
        driver: str = "",
        mode: str = "r",
    ) -> object:
        """Essentially a GDAL Dataset Wrapper

        Parameters
        ----------
        file : str
            _description_

        Returns
        -------
        object
            _description_

        Raises
        ------
        DriverNotFoundError
            _description_
        """

        _BaseIO.__init__(self, file, mode)

        if self.path.suffix not in _GridDriverTable:
            raise DriverNotFoundError("")

        self._driver = gdal.GetDriverByName(driver)

        self.src = None
        self.count = 0
        self._cur_index = 1

        if not self._mode:
            self.src = gdal.Open(str(self.path))
            self.count = self.src.RasterCount

    def __iter__(self):
        self._cur_index = 1
        return self

    def __next__(self):
        if self._cur_index < self.count + 1:
            r = self.src.GetRasterBand(self._cur_index)
            self._cur_index += 1
            return r
        else:
            raise StopIteration

    def __getitem__(
        self,
        oid: int,
    ):
        return self.src.GetRasterBand(oid)

    def close(self):
        _BaseIO.close(self)

        self.src = None
        self._driver = None

        gc.collect()

    def flush(self):
        self.src.FlushCache()

    def reopen(self):
        """_summary_"""

        if not self._closed:
            return self
        return GridSource.__new__(GridSource, self.path)

    @_BaseIO._check_mode
    @_BaseIO._check_state
    def create_band(
        self,
    ):
        """_summary_"""

        self.src.AddBand()
        self.count += 1

    @_BaseIO._check_mode
    @_BaseIO._check_state
    def create_source(
        self,
        shape: tuple,
        nb: int,
        type: int,
        srs: osr.SpatialReference,
    ):
        """_summary_"""

        self.src = self._driver.Create(
            str(self.path), shape[0], shape[1], nb, GridSource._type_map[type]
        )

        self.src.SetSpatialRef(srs)
        self.count = nb

    @_BaseIO._check_state
    def get_bbox(self):
        """_summary_"""

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
        return self.src.GetGeoTransform()

    @_BaseIO._check_state
    def get_srs(self):
        """_summary_"""

        return self.src.GetSpatialRef()

    @_BaseIO._check_mode
    def set_geotransform(self, affine: tuple):
        self.src.SetGeoTransform(affine)

    @_BaseIO._check_mode
    @_BaseIO._check_state
    def set_srs(
        self,
        srs: osr.SpatialReference,
    ):
        self.src.SetSpatialRef(srs)

    @_BaseIO._check_mode
    @_BaseIO._check_state
    def write_array(
        self,
        array: "array",
        band: int,
    ):
        """_summary_"""

        pass


## Open
def open_csv(
    file: str,
    large: bool = False,
) -> object:
    """_summary_

    Parameters
    ----------
    file : str
        _description_

    Returns
    -------
    object
        _description_
    """
    # TODO: If an Exposure CSV contains XY coordinates, save these as a GeomSource object

    if large:
        return CSVLarge(file)
    size = 20 * 1024 * 1024
    if os.path.getsize(file) < size:
        return CSVSmall(file)
    else:
        return CSVLarge(file)


def open_geom(
    file: str,
    driver: str = "",
    mode: str = "r",
):
    """_summary_"""

    return GeomSource(file, driver, mode)


def open_grid(
    file: str,
    driver: str = "",
    mode: str = "r",
):
    """_summary_"""

    return GridSource(file, mode)
