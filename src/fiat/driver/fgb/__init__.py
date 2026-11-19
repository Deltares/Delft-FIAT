"""FlatGeobuf driver."""

import queue as _queue
from multiprocessing.queues import Queue
from typing import Any

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


def _finalize_outputs(
    queue: "Queue[tuple[str, list[Any]]]",
    parameters: dict[str, dict[str, Any]],
    count: int | None = None,
) -> None:
    """Drain worker index records and write the final indexed FlatGeobuf files.

    `count` is the number of record batches (jobs) to wait for, as items put on a
    multiprocessing queue are not instantly available to a non blocking get.
    """
    records_by_path: dict[str, list[Any]] = {key: [] for key in parameters}
    for _ in range(count or 0):
        out_path, records = queue.get(block=True)
        records_by_path.setdefault(out_path, []).extend(records)
    while True:
        try:
            out_path, records = queue.get(block=False)
        except _queue.Empty:
            break
        records_by_path.setdefault(out_path, []).extend(records)

    for out_path, params in parameters.items():
        finalize(
            out_path,
            f"{out_path}.body",
            params["name"],
            params["geom_type"],
            params["col_names"],
            params["col_types"],
            records_by_path.get(out_path, []),
            crs_wkt=params["crs_wkt"],
            crs_org=params["crs_org"],
            crs_code=params["crs_code"],
        )
