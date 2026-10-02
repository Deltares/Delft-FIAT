"""GDAL-free vector I/O for FIAT, backed by the custom Cython FlatGeobuf driver.

Only the FlatGeobuf (``.fgb``) format is supported. The low-level engine lives in the
compiled :mod:`fiat.driver._fgb` package, split across the ``_bindings`` (declarations
and attribute codec), ``_reader`` and ``_writer`` modules; this module is the single
public entry point and re-exports everything (reader/writer, geometry helpers and enum
constants) so the rest of FIAT only needs to import from ``fiat.driver.fgb``.
"""

from pathlib import Path

from pyproj import CRS

from fiat.driver._fgb._reader import (  # noqa: F401
    Feature,
    FlatGeobufReader,
    Geometry,
    make_geometry,
)
from fiat.driver._fgb._serialize import (  # noqa: F401
    CT_BINARY,
    CT_BOOL,
    CT_BYTE,
    CT_DATETIME,
    CT_DOUBLE,
    CT_FLOAT,
    CT_INT,
    CT_JSON,
    CT_LONG,
    CT_SHORT,
    CT_STRING,
    CT_UBYTE,
    CT_UINT,
    CT_ULONG,
    CT_USHORT,
    GT_LINESTRING,
    GT_MULTILINESTRING,
    GT_MULTIPOINT,
    GT_MULTIPOLYGON,
    GT_POINT,
    GT_POLYGON,
    GT_UNKNOWN,
    MAGIC,
)
from fiat.driver._fgb._writer import (  # noqa: F401
    FlatGeobufWriter,
    finalize,
)
from fiat.error import DriverNotFoundError

__all__ = [
    "FlatGeobufDriver",
    "FlatLayer",
    "Feature",
    "Geometry",
    "FlatGeobufReader",
    "FlatGeobufWriter",
    "make_geometry",
    "finalize",
    "FIELD_TYPE_MAP",
    "GEOM_TYPE",
]

# Supported vector extensions (FlatGeobuf only).
GEOM_EXTENSIONS = {".fgb"}

# FIAT field type -> FlatGeobuf ColumnType.
FIELD_TYPE_MAP = {
    "int": CT_LONG,
    "float": CT_DOUBLE,
    "str": CT_STRING,
    int: CT_LONG,
    float: CT_DOUBLE,
    str: CT_STRING,
}

# FlatGeobuf GeometryType by name for convenience.
GEOM_TYPE = {
    "Point": GT_POINT,
    "LineString": GT_LINESTRING,
    "Polygon": GT_POLYGON,
    "MultiPoint": GT_MULTIPOINT,
    "MultiLineString": GT_MULTILINESTRING,
    "MultiPolygon": GT_MULTIPOLYGON,
}


def _crs_from_reader(reader) -> CRS | None:
    """Build a pyproj CRS from a reader's stored CRS metadata."""
    if reader.crs_wkt:
        return CRS.from_user_input(reader.crs_wkt)
    if reader.crs_org and reader.crs_code:
        return CRS.from_user_input(f"{reader.crs_org}:{reader.crs_code}")
    return None


class FlatLayer:
    """A read-only view of a FlatGeobuf layer.

    Wraps a :class:`fiat.driver._fgb._reader.FlatGeobufReader` and exposes the subset of
    the former OGR-layer interface FIAT relies on.
    """

    def __init__(self, reader: FlatGeobufReader):
        self._reader = reader
        self._columns = dict(reader.columns)

    def __iter__(self):
        return iter(self._reader)

    def __len__(self) -> int:
        return len(self._reader)

    ## Properties
    @property
    def crs(self) -> CRS | None:
        """Return the layer CRS as a pyproj CRS."""
        return _crs_from_reader(self._reader)

    @property
    def columns(self) -> tuple:
        """Return the attribute column names."""
        return tuple(self._columns.keys())

    @property
    def fields(self) -> list:
        """Return the attribute field names."""
        return list(self._reader.col_names)

    @property
    def dtypes(self) -> list:
        """Return the FlatGeobuf column type codes of the fields."""
        return list(self._reader.col_types)

    @property
    def geom_type(self) -> int:
        """Return the FlatGeobuf geometry type code."""
        return self._reader.geometry_type

    @property
    def name(self) -> str:
        """Return the layer name."""
        return self._reader.name

    @property
    def size(self) -> int:
        """Return the feature count."""
        return len(self._reader)

    @property
    def bounds(self) -> tuple | None:
        """Return ``(minx, miny, maxx, maxy)`` or None."""
        return self._reader.envelope

    ## Methods
    def reduced_iter(self, si: int, ei: int):
        """Yield features whose 1-based position lies in ``[si, ei]``."""
        return self._reader.reduced_iter(si, ei)

    def select(self, bbox):
        """Yield features intersecting ``bbox`` using the R-tree."""
        return self._reader.select(bbox[0], bbox[1], bbox[2], bbox[3])

    def __getitem__(self, index: int):
        """Return the feature at position ``index`` (0-based)."""
        for i, ft in enumerate(self._reader):
            if i == index:
                return ft
        raise IndexError(index)


class FlatGeobufDriver:
    """A source object for FlatGeobuf vector data.

    Parameters
    ----------
    file : Path | str
        Path to a ``.fgb`` file.
    mode : str, optional
        The I/O mode. ``r`` for reading (default) or ``w`` for writing.
    overwrite : bool, optional
        Kept for API compatibility (unused for reading).
    crs : str, optional
        A spatial reference system string used if the dataset has none.
    """

    def __init__(
        self,
        file: Path | str,
        mode: str = "r",
        overwrite: bool = False,
        crs: str | None = None,
    ):
        self.path = Path(file)
        self.mode_str = mode
        self._crs = crs
        self._reader: FlatGeobufReader | None = None
        self._layer: FlatLayer | None = None
        self._closed = False

        if self.path.suffix.lower() not in GEOM_EXTENSIONS:
            raise DriverNotFoundError(gog="Geometry", path=self.path)

        if mode in ("r", "a"):
            if not self.path.is_file():
                raise FileNotFoundError(
                    f"{self.path.as_posix()} doesn't exist, can't read",
                )
            self._reader = FlatGeobufReader(self.path.as_posix())

    def __repr__(self):
        _mem_loc = f"{id(self):#018x}".upper()
        return f"<{self.__class__.__name__} object at {_mem_loc}>"

    def __reduce__(self):
        return self.__class__, (
            self.path.as_posix(),
            self.mode_str,
            False,
            self._crs,
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    ## Properties
    @property
    def closed(self) -> bool:
        """Return the closed state."""
        return self._closed

    @property
    def layer(self) -> FlatLayer | None:
        """Return the geometry layer."""
        if self._layer is None and self._reader is not None:
            self._layer = FlatLayer(self._reader)
        return self._layer

    @property
    def crs(self) -> CRS | None:
        """Return the CRS as a pyproj CRS."""
        layer = self.layer
        _crs = None
        if layer is not None:
            _crs = layer.crs
        if _crs is None and self._crs is not None:
            _crs = CRS.from_user_input(self._crs)
        return _crs

    ## Methods
    def close(self) -> None:
        """Close the dataset."""
        self._reader = None
        self._layer = None
        self._closed = True

    def flush(self) -> None:
        """No-op (kept for API compatibility)."""

    def reopen(self, mode: str = "r") -> "FlatGeobufDriver":
        """Reopen the dataset."""
        return FlatGeobufDriver(self.path, mode=mode, crs=self._crs)
