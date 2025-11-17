"""Base FIAT utility."""

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
from typing import Any, Generator

import numpy as np
import regex
from osgeo import gdal, ogr, osr

## Config entries
# Building blocks
CHUNK = "chunk"
EXPOSURE = "exposure"
FIAT = "fiat"
FILE = "file"
GEOM = "geom"
GRID = "grid"
HAZARD = "hazard"
INDEX = "index"
METHODS = "methods"
MODEL = "model"
NAME = "name"
OUTPUT = "output"
PATH = "path"
RISK = "risk"
ROUND = "round"  # Hate this one...
SETTINGS = "settings"
SRS = "srs"
STEP_SIZE = "step_size"
THREADS = "threads"
TYPE = "type"
VALUE = "value"
VULNERABILITY = "vulnerability"
# Model settings
MODEL_RISK = f"{MODEL}.{RISK}"
MODEL_SRS = f"{MODEL}.{SRS}"
MODEL_SRS_VALUE = f"{MODEL}.{SRS}.{VALUE}"
MODEL_THREADS = f"{MODEL}.{THREADS}"
MODEL_TYPE = f"{MODEL}.{TYPE}"
# Output
OUTPUT_PATH = f"{OUTPUT}.{PATH}"
# Input
EXPOSURE_GEOM = f"{EXPOSURE}.{GEOM}"
EXPOSURE_GEOM_FILE = f"{EXPOSURE_GEOM}.{FILE}"
EXPOSURE_GEOM_SETTINGS = f"{EXPOSURE_GEOM}.{SETTINGS}"
EXPOSURE_GRID = f"{EXPOSURE}.{GRID}"
EXPOSURE_GRID_FILE = f"{EXPOSURE_GRID}.{FILE}"
EXPOSURE_GRID_SETTINGS = f"{EXPOSURE_GRID}.{SETTINGS}"
HAZARD_FILE = f"{HAZARD}.{FILE}"
HAZARD_SETTINGS = f"{HAZARD}.{SETTINGS}"
HAZARD_TYPE = f"{HAZARD}.{TYPE}"
VULNERABILITY_FILE = f"{VULNERABILITY}.{FILE}"
VULNERABILITY_ROUND = f"{VULNERABILITY}.{ROUND}"  # Also f*ck this one
VULNERABILITY_SETTINGS = f"{VULNERABILITY}.{SETTINGS}"

## Define other string variables
OBJECT_ID = "object_id"

## Define function variables for FIAT
BLACKLIST = type, ModuleType, FunctionType
DD_NEED_IMPLEMENTED = "Dunder method needs to be implemented."
DD_NOT_IMPLEMENTED = "Dunder method not yet implemented."
FILE_ATTRIBUTE_HIDDEN = 0x02
MANDATORY_MODEL_ENTRIES = [
    HAZARD_FILE,
    VULNERABILITY_FILE,
]
MANDATORY_GEOM_ENTRIES = [EXPOSURE_GEOM_FILE]
MANDATORY_GRID_ENTRIES = [EXPOSURE_GRID_FILE]
NEWLINE_CHAR = os.linesep
NEED_IMPLEMENTED = "Method needs to be implemented."
NOT_IMPLEMENTED = "Method not yet implemented."

## Some widely used dictionaries
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


## Patterns
def regex_pattern(
    delimiter: str,
    multi: bool = False,
    nchar: bytes = b"\n",
) -> regex.Pattern:
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
    regex.Pattern
        Compiled regex pattern.
    """
    nchar = nchar.decode()
    if not multi:
        return regex.compile(rf'"[^"]*"(*SKIP)(*FAIL)|{delimiter}'.encode())
    return regex.compile(rf'"[^"]*"(*SKIP)(*FAIL)|{delimiter}|{nchar}'.encode())


# Calculation
def mean(values: list) -> float:
    """Very simple python mean."""
    return sum(values) / len(values)


# Chunking helper functions
def text_chunk_gen(
    h: object,
    pattern: re.Pattern,
    chunk_size: int = 100000,
    nchar: bytes = b"\n",
) -> Generator:
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
            if _res:
                _nlines = _res.count(nchar)
                yield _nlines, pattern.split(_res)
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
) -> Generator:
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


def create_1d_chunks(
    length: int,
    parts: int,
) -> tuple:
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


def _load_diff(
    size: int,
    threads: int,
    diff: int,
    max_threads: int,
) -> float:
    """Difference in load by adding or removed threads."""
    cur = max(threads, 1)
    new = max(threads + diff, 1)
    # Cant take that single thread away, so infinite
    if cur == 1 and cur == new:
        return np.inf
    # Cant exceed system max
    if cur == max_threads and new >= max_threads:
        return 0
    # The difference in load
    diff = (size / cur) - (size / new)
    return abs(diff)


def _diff_table(
    sizes: list[int],
    threads_diss: list[int],
    max_threads: int,
) -> tuple[np.ndarray]:
    """Create a conditional table of load improvements."""
    # Setup the variables
    n = len(sizes)
    flags = np.zeros((n, n))
    diff = np.ones((n, n)) * np.inf
    multi = [item > 1 for item in threads_diss]
    # Loop through the coordinates
    for i, j in product(range(n), range(n)):
        if i == j:  # Diagonal (Cant take from self)
            continue
        if not multi[j]:  # No threads to take
            continue
        val = _load_diff(sizes[i], threads_diss[i], 1, max_threads) - _load_diff(
            sizes[j], threads_diss[j], -1, max_threads
        )
        if val > 0:  # We have a winner
            flags[i, j] = 1
            diff[i, j] = val
    return flags, diff


def distribute_threads(
    size: list[int],
    threads: int,
) -> list[int]:
    """Sort out the weight of the data on all the threads."""
    n = len(size)
    # First estimate of the thread weight
    thread_diss = [round((item / sum(size)) * threads) for item in size]

    # Check for sizes with no threads assigned
    while 0 in thread_diss:
        # Take the first
        idx = thread_diss.index(0)
        thread_diss[idx] = 1
        # Check if there are others with multiple threads
        multi = [i for i, item in enumerate(thread_diss) if item > 1]
        if len(multi) == 0:
            continue
        # See it there is benefit to taking on of those threads
        # For the one with zero threads
        extra = [_load_diff(size[i], thread_diss[i], -1, threads) for i in multi]
        benefit = [size[idx] > item for item in extra]
        if not any(benefit):
            continue
        # Extract one from the one with more than one, dawai
        idx = extra.index(min([item for i, item in enumerate(extra) if benefit[i]]))
        thread_diss[multi[idx]] -= 1

    # Check for at least all the available threads
    while sum(thread_diss) < threads:
        red = [
            _load_diff(item, thread_diss[i], 1, threads) for i, item in enumerate(size)
        ]
        idx = red.index(max(red))
        thread_diss[idx] += 1

    # Redistribute according to size
    while True:
        flags, diff = _diff_table(size, thread_diss, threads)
        if not np.any(flags):
            break
        idxmin = np.argmin(diff)
        thread_diss[idxmin // n] += 1
        thread_diss[idxmin % n] -= 1

    return thread_diss


# Config related stuff
def _flatten_dict_gen(
    d: dict,
    parent_key: str,
    sep: str,
) -> Generator:
    for k, v in d.items():
        new_key = parent_key + sep + k if parent_key else k
        if isinstance(v, MutableMapping):
            yield from flatten_dict(v, new_key, sep=sep).items()
        else:
            yield new_key, v


def flatten_dict(
    d: MutableMapping,
    parent_key: str = "",
    sep: str = ".",
) -> dict:
    """Flatten a dictionary.

    Thanks to this post:
    (https://www.freecodecamp.org/news/how-to-flatten-a-dictionary-in-python-in-4-different-ways/).
    """
    return dict(_flatten_dict_gen(d, parent_key, sep))


# Exposure specific utility
def discover_exp_columns(
    columns: dict,
    type: str,
) -> tuple:
    """Figure out the which are the exposure related columns.

    Parameters
    ----------
    columns : dict
        The columns.
    type : str
        Type of exposure, e.g. damage or affected

    Returns
    -------
    tuple
        Exposure suffix (e.g. structure for damage), index of the columns, \
missing values.
    """
    dmg_idx = {}

    # Get column values
    column_vals = list(columns.keys())

    # Patterns
    fn_pat = rf"^fn_{type}(_\w+)?$"
    max_pat = rf"^max_{type}(_\w+)?$"

    # Filter the current columns
    dmg = re_filter(column_vals, fn_pat)
    dmg_suffix = [re.findall(fn_pat, item)[0] for item in dmg]
    mpd = re_filter(column_vals, max_pat)
    mpd_suffix = [re.findall(max_pat, item)[0] for item in mpd]

    # Check the overlap
    _check = [item in mpd_suffix for item in dmg_suffix]

    # Determine the missing values
    missing = [item for item, b in zip(dmg_suffix, _check) if not b]
    for item in missing:
        dmg_suffix.remove(item)

    fn = {}
    maxv = {}
    for val in dmg_suffix:
        fn.update({val: columns[f"fn_{type}{val}"]})
        maxv.update({val: columns[f"max_{type}{val}"]})
    dmg_idx.update({"fn": fn, "max": maxv})

    return dmg_suffix, dmg_idx, missing


def generate_output_columns(
    specific_columns: tuple | list,
    exposure_types: dict,
    extra: tuple | list = [],
    suffix: tuple | list = [""],
) -> tuple:
    """Generate the output columns."""
    default = specific_columns + ["red_fact"]
    total = []

    # Loop over the exposure types
    for key, value in exposure_types.items():
        default += [f"{key}{item}" for item in value["fn"].keys()]
        total.append(len(default))
        default += [f"total_{key}"]

    total = [item - len(default) for item in total]

    out = []
    if len(suffix) == 1 and not suffix[0]:
        out = default
    else:
        for name in suffix:
            add = [f"{item}_{name}" for item in default]
            out += add

    out += [f"{x}_{y}" for x, y in product(extra, exposure_types.keys())]

    return out, len(default), total


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
) -> dict:
    """Read grid source information.

    Thanks to:
    https://stackoverflow.com/questions/72059815/how-to-retrieve-all-variable-names-within-a-netcdf-using-gdal.
    """
    info = gdal.Info(gr, options=gdal.InfoOptions(format=format))
    return info


def read_gridsource_layers(
    gr: gdal.Dataset,
) -> dict | None:
    """Read the layers of a gridsource."""
    sd = gr.GetSubDatasets()

    out = {}

    for item in sd:
        path = item[0]
        ds = path.split(":")[-1].strip()
        out[ds] = path

    if len(out) == 0:
        return None
    return out


def _check_geom_driver_capabilities(
    idx: int,
    type: str,
) -> tuple[gdal.Driver, list] | tuple[None]:
    """Return driver when it has the necessary capabilities."""
    driver = gdal.GetDriver(idx)
    # Check the create capability
    if not driver.GetMetadataItem(gdal.DCAP_CREATE):
        return None, None
    # Check on vector driver
    if (
        type == gdal.DCAP_VECTOR
        and not driver.GetMetadataItem(gdal.DCAP_VECTOR)
        and not driver.GetMetadataItem(gdal.DCAP_CREATE_LAYER)
    ):
        return None, None
    # Check on Raster driver
    if (
        type == gdal.DCAP_RASTER
        and not driver.GetMetadataItem(gdal.DCAP_RASTER)
        and not driver.GetMetadataItem(gdal.DCAP_CREATECOPY)
    ):
        return None, None
    # Get the extension
    ext = driver.GetMetadataItem(gdal.DMD_EXTENSION) or driver.GetMetadataItem(
        gdal.DMD_EXTENSIONS
    )
    # If None, cant do anything
    if ext is None:
        return None, None
    # Get the extension from the returned str or list
    if len(ext.split(" ")) > 1:
        exts = ext.split(" ")
        if driver.ShortName.lower() in exts:
            ext = driver.ShortName.lower()
        else:
            ext = ext.split(" ")[-1]
    return driver, ext


def _create_driver_map(
    type: str,
) -> dict:
    """Create a map of geometry drivers."""
    drivers = {}
    count = gdal.GetDriverCount()

    for idx in range(count):
        driver, ext = _check_geom_driver_capabilities(idx, type=type)
        if driver is None:
            continue
        if len(ext) > 0:
            ext = "." + ext
            drivers[ext] = driver.ShortName

    return drivers


GEOM_DRIVER_MAP = _create_driver_map(type=gdal.DCAP_VECTOR)
GEOM_DRIVER_MAP[""] = "MEM"
GRID_DRIVER_MAP = _create_driver_map(type=gdal.DCAP_RASTER)
GRID_DRIVER_MAP[""] = "MEM"


# I/O stuff
def create_dir(
    root: Path | str,
    path: Path | str,
) -> Path:
    """Create directory when it does not yet exist."""
    _p = Path(path)
    if not _p.is_absolute():
        _p = Path(root, _p)
    generic_directory_check(_p)
    return _p


def generic_directory_check(
    path: Path | str,
) -> Path:
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
        raise FileNotFoundError(f"{path.as_posix()} is not a valid path")
    return path


# Misc.
def find_duplicates(elements: tuple | list) -> list | None:
    """Find duplicate elements in an iterable object."""
    uni = list(set(elements))
    counts = [elements.count(elem) for elem in uni]
    dup = [elem for _i, elem in enumerate(uni) if counts[_i] > 1]
    if not dup:
        return None
    return dup


def re_filter(values, pat) -> list:
    """Quickly filter values based on a pattern match."""
    result = []
    pat = os.path.normcase(pat)
    match = re.compile(pat).match
    for val in values:
        if match(val):
            result.append(val)
    return result


def get_module_attr(module: str, attr: str) -> Any:
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
) -> int:
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
) -> int:
    """Detemine the number of decimals."""
    ndec = math.floor(math.log(e) / math.log(base))
    return abs(ndec)


def replace_empty(l: list) -> list:
    """Replace empty values by None in a string (i.e. between delimiters)."""
    return ["nan" if not e else e.decode() for e in l]
