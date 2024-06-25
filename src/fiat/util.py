"""Base FIAT utility."""

import ctypes
import math
import os
import platform
import re
import sys
from collections.abc import MutableMapping
from gc import get_referents
from itertools import product
from pathlib import Path
from types import FunctionType, ModuleType

import regex
from osgeo import gdal

# Define the variables for FIAT
BLACKLIST = type, ModuleType, FunctionType
DD_NEED_IMPLEMENTED = "Dunder method needs to be implemented."
DD_NOT_IMPLEMENTED = "Dunder method not yet implemented."
FILE_ATTRIBUTE_HIDDEN = 0x02
NEWLINE_CHAR = os.linesep
NEED_IMPLEMENTED = "Method needs to be implemented."
NOT_IMPLEMENTED = "Method not yet implemented."


# Some widely used dictionaries
_dtypes = {
    0: 3,
    1: 2,
    2: 1,
}

_dtypes_reversed = {
    0: str,
    1: int,
    2: float,
    3: str,
}

_dtypes_from_string = {
    "float": float,
    "int": int,
    "str": str,
}


def regex_pattern(
    delimiter: str,
    multi: bool = False,
):
    """_summary_."""
    if not multi:
        return regex.compile(rf'"[^"]*"(*SKIP)(*FAIL)|{delimiter}'.encode())
    return regex.compile(rf'"[^"]*"(*SKIP)(*FAIL)|{delimiter}|{NEWLINE_CHAR}'.encode())


# Calculation
def mean(values: list):
    """Very simple python mean."""
    return sum(values) / len(values)


# Chunking helper functions
def _text_chunk_gen(
    h: object,
    pattern: re.Pattern,
    chunk_size: int = 100000,
):
    _res = b""
    while True:
        t = h.read(chunk_size)
        if not t:
            break
        t = _res + t
        try:
            t, _res = t.rsplit(
                NEWLINE_CHAR.encode(),
                1,
            )
        except Exception:
            _res = b""
        _nlines = t.count(NEWLINE_CHAR.encode())
        sd = pattern.split(t)
        del t
        yield _nlines, sd


def create_windows(
    shape: tuple,
    chunk: tuple,
):
    """_summary_."""
    _x, _y = shape
    _lu = tuple(
        product(
            range(0, _x, chunk[0]),
            range(0, _y, chunk[1]),
        ),
    )
    for _l, _u in _lu:
        w = min(chunk[0], _x - _l)
        h = min(chunk[1], _y - _u)
        yield (
            _l,
            _u,
            w,
            h,
        )


def create_1d_chunk(
    length: int,
    parts: int,
):
    """Create chunks for 1d vector data."""
    part = math.ceil(
        length / parts,
    )
    series = list(
        range(0, length, part),
    ) + [length]
    _series = series.copy()
    _series.remove(_series[0])
    series = [_i + 1 for _i in series]

    chunks = tuple(
        zip(series[:-1], _series),
    )

    return chunks


# Config related stuff
def _flatten_dict_gen(d, parent_key, sep):
    for k, v in d.items():
        new_key = parent_key + sep + k if parent_key else k
        if isinstance(v, MutableMapping):
            yield from flatten_dict(v, new_key, sep=sep).items()
        else:
            yield new_key, v


def flatten_dict(d: MutableMapping, parent_key: str = "", sep: str = "."):
    """Flatten a dictionary.

    Thanks to this post:
    (https://www.freecodecamp.org/news/how-to-flatten-a-dictionary-in-python-in-4-different-ways/).
    """
    return dict(_flatten_dict_gen(d, parent_key, sep))


# Exposure specific utility
def gen_new_columns():
    """_summary_."""
    pass


# GIS related utility
def _read_gridsource_info(
    gr: gdal.Dataset,
    format: str = "json",
):
    """_summary_.

    Thanks to:
    https://stackoverflow.com/questions/72059815/how-to-retrieve-all-variable-names-within-a-netcdf-using-gdal.
    """
    info = gdal.Info(gr, options=gdal.InfoOptions(format=format))
    return info


def _read_gridsrouce_layers(
    gr: gdal.Dataset,
):
    """_summary_."""
    sd = gr.GetSubDatasets()

    out = {}

    for item in sd:
        path = item[0]
        ds = path.split(":")[-1].strip()
        out[ds] = path

    return out


def _read_gridsource_layers_from_info(
    info: dict,
):
    """_summary_.

    Thanks to:
    https://stackoverflow.com/questions/72059815/how-to-retrieve-all-variable-names-within-a-netcdf-using-gdal.
    """
    _sub_data_keys = [x for x in info["metadata"]["SUBDATASETS"].keys() if "_NAME" in x]
    _sub_data_vars = [info["metadata"]["SUBDATASETS"][x] for x in _sub_data_keys]

    pass


def _create_geom_driver_map():
    """_summary_."""
    geom_drivers = {}
    _c = gdal.GetDriverCount()

    for idx in range(_c):
        dr = gdal.GetDriver(idx)
        if dr.GetMetadataItem(gdal.DCAP_VECTOR):
            if dr.GetMetadataItem(gdal.DCAP_CREATE) or dr.GetMetadataItem(
                gdal.DCAP_CREATE_LAYER
            ):
                ext = dr.GetMetadataItem(gdal.DMD_EXTENSION) or dr.GetMetadataItem(
                    gdal.DMD_EXTENSIONS
                )
                if ext is None:
                    continue
                if len(ext.split(" ")) > 1:
                    exts = ext.split(" ")
                    if dr.ShortName.lower() in exts:
                        ext = dr.ShortName.lower()
                    else:
                        ext = ext.split(" ")[-1]
                if len(ext) > 0:
                    ext = "." + ext
                    geom_drivers[ext] = dr.ShortName

    return geom_drivers


GEOM_DRIVER_MAP = _create_geom_driver_map()
GEOM_DRIVER_MAP[""] = "Memory"


def _create_grid_driver_map():
    """_summary_."""
    grid_drivers = {}
    _c = gdal.GetDriverCount()

    for idx in range(_c):
        dr = gdal.GetDriver(idx)
        if dr.GetMetadataItem(gdal.DCAP_RASTER):
            if dr.GetMetadataItem(gdal.DCAP_CREATE) or dr.GetMetadataItem(
                gdal.DCAP_CREATECOPY
            ):
                ext = dr.GetMetadataItem(gdal.DMD_EXTENSION) or dr.GetMetadataItem(
                    gdal.DMD_EXTENSIONS
                )
                if ext is None:
                    continue
                if len(ext.split(" ")) > 1:
                    exts = ext.split(" ")
                    if dr.ShortName.lower() in exts:
                        ext = dr.ShortName.lower()
                    else:
                        ext = ext.split(" ")[-1]
                if len(ext) > 0:
                    ext = "." + ext
                    grid_drivers[ext] = dr.ShortName

    return grid_drivers


GRID_DRIVER_MAP = _create_grid_driver_map()
GRID_DRIVER_MAP[""] = "MEM"


# I/O stuff
def generic_folder_check(
    path: Path | str,
):
    """_summary_.

    Parameters
    ----------
    path : Path | str
        _description_
    """
    path = Path(path)
    if not path.exists():
        path.mkdir(parents=True)


def create_hidden_folder(
    path: Path | str,
):
    """_summary_.

    Parameters
    ----------
    path : Path | str
        _description_
    """
    path = Path(path)
    if not path.stem.startswith("."):
        path = Path(path.parent, f".{path.stem}")
    generic_folder_check(path)

    if platform.system().lower() == "windows":
        r = ctypes.windll.kernel32.SetFileAttributesW(
            str(path),
            FILE_ATTRIBUTE_HIDDEN,
        )

        if not r:
            raise OSError("")


def generic_path_check(
    path: str,
    root: str,
) -> Path:
    """_summary_.

    Parameters
    ----------
    path : str
        _description_
    root : str
        _description_

    Returns
    -------
    Path
        _description_

    Raises
    ------
    FileNotFoundError
        _description_
    """
    path = Path(path)
    if not path.is_absolute():
        path = Path(root, path)
    if not (path.is_file() | path.is_dir()):
        raise FileNotFoundError(f"{str(path)} is not a valid path")
    return path


# Misc.
def object_size(obj):
    """Calculate the actual size of an object (bit overestimated).

    Thanks to this post on stackoverflow:
    (https://stackoverflow.com/questions/449560/how-do-i-determine-the-size-of-an-object-in-python).

    Just for internal and debugging uses
    """
    if isinstance(obj, BLACKLIST):
        raise TypeError("getsize() does not take argument of type: " + str(type(obj)))

    seen_ids = set()
    size = 0
    objects = [obj]

    while objects:
        need_referents = []
        for obj in objects:
            if not isinstance(obj, BLACKLIST) and id(obj) not in seen_ids:
                seen_ids.add(id(obj))
                size += sys.getsizeof(obj)
                need_referents.append(obj)
        objects = get_referents(*need_referents)

    return size


# Objects for dummy usage
class DoNotCall(type):
    """_summary_."""

    def __call__(
        self,
        *args,
        **kwargs,
    ):
        """_summary_."""
        raise AttributeError("Cannot initialize directly, needs a contructor")


class DummyLock:
    """Mimic Lock functionality while doing nothing."""

    def acquire(self):
        """Call dummy acquire."""
        pass

    def release(self):
        """Call dummy release."""
        pass


# Typing related stuff
def deter_type(
    e: bytes,
    l: int,
):
    """_summary_."""
    f_p = rf"((^(-)?\d+(\.\d*)?(E(\+|\-)?\d+)?)$|^$)(\n((^(-)?\d+(\.\d*)?(E(\+|\-)?\d+)?)$|^$)){{{l}}}"  # noqa: E501
    f_c = re.compile(bytes(f_p, "utf-8"), re.MULTILINE | re.IGNORECASE)

    i_p = rf"((^(-)?\d+(E(\+|\-)?\d+)?)$)(\n((^(-)?\d+(E(\+|\-)?\d+)?)$)){{{l}}}"
    i_c = re.compile(bytes(i_p, "utf-8"), re.MULTILINE | re.IGNORECASE)

    l = (
        bool(f_c.match(e)),
        bool(i_c.match(e)),
    )
    return _dtypes[sum(l)]


def deter_dec(
    e: float,
    base: float = 10.0,
):
    """_summary_."""
    ndec = math.floor(math.log(e) / math.log(base))
    return abs(ndec)


def replace_empty(l: list):
    """_summary_."""
    return ["nan" if not e else e.decode() for e in l]
