"""FlatGeobuf driver."""

from fiat.driver.vector import VectorProfile

from .reader import (
    Feature,
    FlatGeobufReader,
    Geometry,
    make_geometry,
)
from .serialize import (  # noqa: F401
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
from .writer import (
    FlatGeobufWriter,
    finalize,
)

__all__ = [
    "Feature",
    "FIELD_TYPE_MAP",
    "FlatGeobufReader",
    "FlatGeobufWriter",
    "GEOM_TYPE",
    "Geometry",
    "VectorProfile",
    "finalize",
    "make_geometry",
]

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
