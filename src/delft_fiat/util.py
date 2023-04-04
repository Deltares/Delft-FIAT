import math
import os
import re
import sys
from gc import get_referents
from pathlib import Path
from types import ModuleType, FunctionType

BLACKLIST = type, ModuleType, FunctionType

_GeomDriverTable = {
    "": "Memory",
    ".csv": "CSV",
    ".gdb": "FileGDB",
    ".geojson": "GeoJSON",
    ".gpkg": "GPKG",
    ".nc": "netCDF",
    ".shp": "ESRI Shapefile",
}

_GridDriverTable = {
    "": "MEM",
    ".nc": "netCDF",
    ".tif": "GTiff",
    ".vrt": "VRT",
}

_dtypes = {
    0: 3,
    1: 2,
    2: 1,
}

_dtypes_reversed = {
    1: int,
    2: float,
    3: str,
}


def replace_empty(l: list):
    """_summary_"""

    return ["nan" if not e else e.decode() for e in l]


def deter_type(
    e: bytes,
    l: int,
):
    """_summary_"""

    f_p = rf"((^(-)?\d+(\.\d*)*(E(\+|\-){1}\d+)*)|^$)(\n((^(-)?\d+(\.\d*)*(E(\+|\-){1}\d+)*)|^$)){{{l}}}"
    f_c = re.compile(bytes(f_p, "utf-8"), re.MULTILINE)

    i_p = rf"(^(-)?\d+(E(\+|\-){1}\d+)*|^$)(\n(^(-)?\d+(E(\+|\-){1}\d+)*|^$)){{{l}}}"
    i_c = re.compile(bytes(i_p, "utf-8"), re.MULTILINE)

    # l = (
    #     bool(re.match(b"(^(-)?\d+)|^$|nan", e)),
    #     bool(re.match(b"^(-)?\d+\.\d+", e)),
    # )

    l = (
        bool(f_c.match(e)),
        bool(i_c.match(e)),
    )
    return _dtypes[sum(l)]


def deter_dec(
    e: float,
    base: float = 10.0,
):
    """_summary_"""

    ndec = math.floor(math.log(e) / math.log(base))
    return abs(ndec)


def object_size(obj):
    """Actual size of an object (bit overestimated)
    Thanks to this post on stackoverflow:
    (https://stackoverflow.com/questions/449560/how-do-i-determine-the-size-of-an-object-in-python)

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


def generic_folder_check(
    path: str,
):
    """_summary_

    Parameters
    ----------
    path : str
        _description_
    """

    path = Path(path)
    if not path.exists():
        os.makedirs(path)


def generic_path_check(
    path: str,
    root: str,
) -> Path:
    """_summary_

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
