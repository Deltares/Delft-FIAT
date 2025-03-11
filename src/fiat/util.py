"""Base FIAT utility."""

import fnmatch
import importlib
import math
import os
import re
import sys
from collections.abc import MutableMapping
from gc import get_referents
from itertools import product
from pathlib import Path
from types import FunctionType, ModuleType

import regex
from osgeo import gdal, ogr, osr

# Define the variables for FIAT
BLACKLIST = type, ModuleType, FunctionType
DD_NEED_IMPLEMENTED = "Dunder method needs to be implemented."
DD_NOT_IMPLEMENTED = "Dunder method not yet implemented."
FILE_ATTRIBUTE_HIDDEN = 0x02
MANDATORY_MODEL_ENTRIES = [
    "output.path",
    "hazard.file",
    "hazard.risk",
    "vulnerability.file",
]
MANDATORY_GEOM_ENTRIES = [
    r"exposure.geom.file\d+",
]
MANDATORY_GRID_ENTRIES = ["exposure.grid.file"]
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

_fields_type_map = {
    "int": ogr.OFTInteger64,
    "float": ogr.OFTReal,
    "str": ogr.OFTString,
}


def regex_pattern(delimiter: str, multi: bool = False, nchar: bytes = b"\n"):
    """Create a regex pattern.

    Parameters
    ----------
    delimiter : str
        The delimiter of the text.
    multi : bool, optional
        Whether is spans multiple lines or not, by default False
    nchar : bytes, optional
        The newline character, by default b"\n"

    Returns
    -------
    _type_
        _description_
    """
    nchar = nchar.decode()
    if not multi:
        return regex.compile(rf'"[^"]*"(*SKIP)(*FAIL)|{delimiter}'.encode())
    return regex.compile(rf'"[^"]*"(*SKIP)(*FAIL)|{delimiter}|{nchar}'.encode())


# Calculation
def mean(values: list):
    """Very simple python mean."""
    return sum(values) / len(values)


# Chunking helper functions
def text_chunk_gen(
    h: object,
    pattern: re.Pattern,
    chunk_size: int = 100000,
    nchar: bytes = b"\n",
):
    """Read and split text in chunks.

    Parameters
    ----------
    h : object
        A stream handler.
    pattern : re.Pattern
        Pattern on how to split the text.
    chunk_size : int, optional
        The chunk size in characters, by default 100000
    nchar : bytes, optional
        The newline character, by default b"\n"

    Returns
    -------
    tuple
        Number of lines, split text
    """
    _res = b""
    while True:
        t = h.read(chunk_size)
        if not t:
            break
        t = _res + t
        try:
            t, _res = t.rsplit(
                nchar,
                1,
            )
        except Exception:
            _res = b""
        _nlines = t.count(nchar)
        sd = pattern.split(t)
        del t
        yield _nlines, sd


def create_windows(
    shape: tuple,
    chunk: tuple,
):
    """Create chunk windows from a grid.

    Parameters
    ----------
    shape : tuple
        Shape of the grid.
    chunk : tuple
        The chunk size.

    Returns
    -------
    tuple
        Tuple containing the upperleft x and y corner and the width and height
    """
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
def discover_exp_columns(
    columns: dict,
    type: str,
):
    """Figure out the which are the exposure related columns.

    Parameters
    ----------
    columns : dict
        The columns.
    type : str
        Type of exposure, e.g. damage or affected

    Returns
    -------
    Tuple
        Exposure suffix (e.g. structure for damage), index of the columns, \
missing values.
    """
    dmg_idx = {}

    # Get column values
    column_vals = list(columns.keys())

    # Filter the current columns
    dmg = fnmatch.filter(column_vals, f"fn_{type}_*")
    dmg_suffix = [item.split("_")[-1].strip() for item in dmg]
    mpd = fnmatch.filter(column_vals, f"max_{type}_*")
    mpd_suffix = [item.split("_")[-1].strip() for item in mpd]

    # Check the overlap
    _check = [item in mpd_suffix for item in dmg_suffix]

    # Determine the missing values
    missing = [item for item, b in zip(dmg_suffix, _check) if not b]
    for item in missing:
        dmg_suffix.remove(item)

    fn = {}
    maxv = {}
    for val in dmg_suffix:
        fn.update({val: columns[f"fn_{type}_{val}"]})
        maxv.update({val: columns[f"max_{type}_{val}"]})
    dmg_idx.update({"fn": fn, "max": maxv})

    return dmg_suffix, dmg_idx, missing


def generate_output_columns(
    specific_columns: tuple | list,
    exposure_types: dict,
    extra: tuple | list = [],
    suffix: tuple | list = [""],
):
    """Generate the output columns."""
    default = specific_columns + ["red_fact"]
    total_idx = []

    # Loop over the exposure types
    for key, value in exposure_types.items():
        default += [f"{key}_{item}" for item in value["fn"].keys()]
        total_idx.append(len(default))
        default += [f"total_{key}"]

    total_idx = [item - len(default) for item in total_idx]

    out = []
    if len(suffix) == 1 and not suffix[0]:
        out = default
    else:
        for name in suffix:
            add = [f"{item}_{name}" for item in default]
            out += add

    out += [f"{x}_{y}" for x, y in product(extra, exposure_types.keys())]

    return out, len(default), total_idx


# GIS related utility
def get_srs_repr(
    srs: osr.SpatialReference,
) -> str:
    """Get a representation of a spatial reference system object.

    Parameters
    ----------
    srs : osr.SpatialReference
        Spatial reference system.

    Returns
    -------
    str
        Representing string.
    """
    if srs is None:
        raise ValueError("'srs' can not be 'None'.")
    _auth_c = srs.GetAuthorityCode(None)
    _auth_n = srs.GetAuthorityName(None)

    if _auth_c is None or _auth_n is None:
        return srs.ExportToProj4()

    return f"{_auth_n}:{_auth_c}"


def read_gridsource_info(
    gr: gdal.Dataset,
    format: str = "json",
):
    """Read grid source information.

    Thanks to:
    https://stackoverflow.com/questions/72059815/how-to-retrieve-all-variable-names-within-a-netcdf-using-gdal.
    """
    info = gdal.Info(gr, options=gdal.InfoOptions(format=format))
    return info


def read_gridsource_layers(
    gr: gdal.Dataset,
):
    """Read the layers of a gridsource."""
    sd = gr.GetSubDatasets()

    out = {}

    for item in sd:
        path = item[0]
        ds = path.split(":")[-1].strip()
        out[ds] = path

    return out


def _create_geom_driver_map(
    write: bool = False,
):
    """Create a map of geometry drivers."""
    geom_drivers = {}
    _c = gdal.GetDriverCount()

    for idx in range(_c):
        dr = gdal.GetDriver(idx)
        if dr.GetMetadataItem(gdal.DCAP_VECTOR):
            edit = dr.GetMetadataItem(gdal.DCAP_DELETE_FIELD)
            if write and edit is None:
                continue
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


GEOM_READ_DRIVER_MAP = _create_geom_driver_map()
GEOM_WRITE_DRIVER_MAP = _create_geom_driver_map(write=True)
GEOM_WRITE_DRIVER_MAP[""] = "Memory"


def _create_grid_driver_map():
    """Create a map of grid drivers."""
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
def create_dir(
    root: Path | str,
    path: Path | str,
):
    """Create directory when it does not yet exist."""
    _p = Path(path)
    if not _p.is_absolute():
        _p = Path(root, _p)
    generic_folder_check(_p)
    return _p


def generic_folder_check(
    path: Path | str,
):
    """Check if a directory exists.

    Parameters
    ----------
    path : Path | str
        Path to the directory.
    """
    path = Path(path)
    if not path.exists():
        path.mkdir(parents=True)


def generic_path_check(
    path: str,
    root: str,
) -> Path:
    """Check whether a file exists.

    Parameters
    ----------
    path : str
        Path to the file.
    root : str
        Current root directory.

    Returns
    -------
    Path
        Absolute path to the file.
    """
    path = Path(path)
    if not path.is_absolute():
        path = Path(root, path)
    if not (path.is_file() | path.is_dir()):
        raise FileNotFoundError(f"{str(path)} is not a valid path")
    return path


# Logging utility
def progressbar(
    iteration: int,
    total: int,
    prefix: str = "",
    suffix: str = "",
    decimals: int = 1,
    bar_length: int = 50,
):
    """Call in a loop to create terminal progress bar.

    @params:
        iteration   - Required  : current iteration (Int)
        total       - Required  : total iterations (Int)
        prefix      - Optional  : prefix string (Str)
        suffix      - Optional  : suffix string (Str)
        decimals    - Optional  : positive number of decimals in percent complete (Int)
        bar_length  - Optional  : character length of bar (Int)
    """
    str_format = "{0:." + str(decimals) + "f}"
    percents = str_format.format(100 * (iteration / float(total)))
    filled_length = int(round(bar_length * iteration / float(total)))
    bar = "█" * filled_length + "-" * (bar_length - filled_length)

    (sys.stdout.write("\r%s |%s| %s%s %s" % (prefix, bar, percents, "%", suffix)),)

    if iteration == total:
        sys.stdout.write("\n")
    sys.stdout.flush()


# Misc.
def find_duplicates(elements: tuple | list):
    """Find duplicate elements in an iterable object."""
    uni = list(set(elements))
    counts = [elements.count(elem) for elem in uni]
    dup = [elem for _i, elem in enumerate(uni) if counts[_i] > 1]
    if not dup:
        return None
    return dup


def get_module_attr(module: str, attr: str):
    """Quickly get attribute from a module dynamically."""
    module = importlib.import_module(module)
    out = getattr(module, attr)
    module = None
    return out


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
class DummyLock:
    """Mimic Lock functionality while doing nothing."""

    def acquire(self):
        """Call dummy acquire."""
        pass

    def release(self):
        """Call dummy release."""
        pass


class DummyWriter:
    """Mimic the behaviour of an object that is capable of writing."""

    def __init__(self, *args, **kwargs):
        pass

    def close(self):
        """Call dummy close."""
        pass

    def write(self, *args):
        """Call dummy write."""
        pass

    def write_iterable(self, *args):
        """Call dummy write iterable."""
        pass


# Typing related stuff
def deter_type(
    e: bytes,
    l: int,
):
    """Detemine the type of a column of text.

    Parameters
    ----------
    e : bytes
        The bytes containing the text.
    l : int
        Number of occurances.

    Returns
    -------
    int
        Type of the column expressed by an integer.
    """
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
    """Detemine the number of decimals."""
    ndec = math.floor(math.log(e) / math.log(base))
    return abs(ndec)


def replace_empty(l: list):
    """Replace empty values by None in a string (i.e. between delimiters)."""
    return ["nan" if not e else e.decode() for e in l]
