from pathlib import Path

import numpy as np
import pytest
from pyproj import CRS

from fiat.driver.fgb import (
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
    GT_POINT,
    GT_POLYGON,
    Feature,
    FlatGeobufDriver,
    FlatGeobufReader,
    FlatGeobufWriter,
    Geometry,
    make_geometry,
)
from fiat.util import get_crs_repr


def _square(minx: float, miny: float, maxx: float, maxy: float) -> Geometry:
    """Build a closed square polygon geometry."""
    xy = [minx, miny, maxx, miny, maxx, maxy, minx, maxy, minx, miny]
    return make_geometry(GT_POLYGON, xy, ends=[5])


def _roundtrip(path: Path, geom: Geometry) -> FlatGeobufReader:
    """Write a single feature and return a reader over the result."""
    writer = FlatGeobufWriter(
        path.as_posix(),
        col_names=["object_id", "name"],
        col_types=[CT_INT, CT_STRING],
        geom_type=geom.type,
        name=path.stem,
    )
    writer.add_feature(geom.xy, geom.ends, geom.parts, [7, path.stem])
    writer.finalize()
    return FlatGeobufReader(path.as_posix())


def test_fgb_roundtrip(tmp_path: Path):
    # Write two polygon features with attributes
    path = Path(tmp_path, "roundtrip.fgb")
    crs = CRS.from_epsg(4326)
    geometries = [_square(0.0, 0.0, 1.0, 1.0), _square(2.0, 2.0, 3.0, 4.0)]
    values = [[1, 2.5, "one"], [2, 5.0, "two"]]
    writer = FlatGeobufWriter(
        path.as_posix(),
        col_names=["object_id", "score", "name"],
        col_types=[CT_INT, CT_DOUBLE, CT_STRING],
        geom_type=GT_POLYGON,
        name="roundtrip",
        crs_wkt=crs.to_wkt(),
        crs_org="EPSG",
        crs_code=4326,
    )
    for geom, row in zip(geometries, values):
        writer.add_feature(geom.xy, geom.ends, geom.parts, row)
    writer.finalize()

    # Read the header back
    reader = FlatGeobufReader(path.as_posix())

    # Assert the metadata survived
    assert reader.name == "roundtrip"
    assert len(reader) == 2
    assert reader.geometry_type == GT_POLYGON
    assert reader.col_names == ["object_id", "score", "name"]
    assert reader.col_types == [CT_INT, CT_DOUBLE, CT_STRING]
    assert reader.envelope == (0.0, 0.0, 3.0, 4.0)
    assert reader.crs_org == "EPSG"
    assert reader.crs_code == 4326


def test_fgb_roundtrip_features(tmp_path: Path):
    # Write two polygon features
    path = Path(tmp_path, "roundtrip.fgb")
    geometries = [_square(0.0, 0.0, 1.0, 1.0), _square(2.0, 2.0, 3.0, 4.0)]
    values = [[1, "one"], [2, "two"]]
    writer = FlatGeobufWriter(
        path.as_posix(),
        col_names=["object_id", "name"],
        col_types=[CT_INT, CT_STRING],
        geom_type=GT_POLYGON,
        name="roundtrip",
    )
    for geom, row in zip(geometries, values):
        writer.add_feature(geom.xy, geom.ends, geom.parts, row)
    writer.finalize()

    # Read the features back, ordered by id
    reader = FlatGeobufReader(path.as_posix())
    features = sorted(reader, key=lambda ft: ft.get_field("object_id"))

    # Assert attributes and geometry survived
    assert all(isinstance(ft, Feature) for ft in features)
    assert features[0].values == values[0]
    assert features[1].values == values[1]
    np.testing.assert_array_almost_equal(
        features[0].geometry.coords, geometries[0].coords
    )
    assert features[0].geometry.envelope() == (0.0, 0.0, 1.0, 1.0)
    assert features[1].geometry.envelope() == (2.0, 2.0, 3.0, 4.0)


def test_fgb_layer(tmp_path: Path):
    # Write a small layer
    path = Path(tmp_path, "roundtrip.fgb")
    crs = CRS.from_epsg(4326)
    geom = _square(0.0, 0.0, 1.0, 1.0)
    writer = FlatGeobufWriter(
        path.as_posix(),
        col_names=["object_id"],
        col_types=[CT_INT],
        geom_type=GT_POLYGON,
        name="roundtrip",
        crs_wkt=crs.to_wkt(),
        crs_org="EPSG",
        crs_code=4326,
    )
    writer.add_feature(geom.xy, geom.ends, geom.parts, [1])
    writer.finalize()

    # Open through the driver
    driver = FlatGeobufDriver(path)
    layer = driver.layer

    # Assert the layer properties
    assert layer.name == "roundtrip"
    assert layer.size == 1
    assert layer.bounds == (0.0, 0.0, 1.0, 1.0)
    assert layer.geom_type == GT_POLYGON
    assert get_crs_repr(driver.crs) == "EPSG:4326"

    # A bbox selection returns the overlapping feature
    selected = list(layer.select((0.0, 0.0, 0.5, 0.5)))
    assert len(selected) == 1
    assert selected[0].get_field("object_id") == 1


def test_fgb_roundtrip_point(tmp_path: Path, fgb_point: Geometry):
    # Round trip a point geometry
    reader = _roundtrip(Path(tmp_path, "point.fgb"), fgb_point)
    feature = next(iter(reader))

    # Assert the geometry survived
    assert feature.geometry.type == fgb_point.type
    assert feature.geometry.envelope() == fgb_point.envelope()
    np.testing.assert_array_almost_equal(feature.geometry.coords, fgb_point.coords)


def test_fgb_roundtrip_multipoint(tmp_path: Path, fgb_multipoint: Geometry):
    # Round trip a multipoint geometry
    reader = _roundtrip(Path(tmp_path, "multipoint.fgb"), fgb_multipoint)
    feature = next(iter(reader))

    # Assert the geometry survived
    assert feature.geometry.type == fgb_multipoint.type
    np.testing.assert_array_almost_equal(feature.geometry.coords, fgb_multipoint.coords)


def test_fgb_roundtrip_linestring(tmp_path: Path, fgb_linestring: Geometry):
    # Round trip a linestring geometry
    reader = _roundtrip(Path(tmp_path, "linestring.fgb"), fgb_linestring)
    feature = next(iter(reader))

    # Assert the geometry survived
    assert feature.geometry.type == fgb_linestring.type
    np.testing.assert_array_almost_equal(feature.geometry.coords, fgb_linestring.coords)


def test_fgb_roundtrip_multilinestring(tmp_path: Path, fgb_multilinestring: Geometry):
    # Round trip a multilinestring geometry
    reader = _roundtrip(Path(tmp_path, "multilinestring.fgb"), fgb_multilinestring)
    feature = next(iter(reader))

    # Assert the geometry and its ring boundaries survived
    assert feature.geometry.type == fgb_multilinestring.type
    np.testing.assert_array_equal(feature.geometry.ends, fgb_multilinestring.ends)
    np.testing.assert_array_almost_equal(
        feature.geometry.coords, fgb_multilinestring.coords
    )


def test_fgb_roundtrip_polygon_hole(tmp_path: Path, fgb_polygon_hole: Geometry):
    # Round trip a polygon with a hole
    reader = _roundtrip(Path(tmp_path, "polygon_hole.fgb"), fgb_polygon_hole)
    feature = next(iter(reader))

    # Assert the ring layout survived
    assert feature.geometry.type == fgb_polygon_hole.type
    np.testing.assert_array_equal(feature.geometry.ends, fgb_polygon_hole.ends)
    np.testing.assert_array_almost_equal(
        feature.geometry.coords, fgb_polygon_hole.coords
    )


def test_fgb_roundtrip_multipolygon(tmp_path: Path, fgb_multipolygon: Geometry):
    # Round trip a multipolygon geometry
    reader = _roundtrip(Path(tmp_path, "multipolygon.fgb"), fgb_multipolygon)
    feature = next(iter(reader))

    # Assert the ring and part layout survived
    assert feature.geometry.type == fgb_multipolygon.type
    np.testing.assert_array_equal(feature.geometry.ends, fgb_multipolygon.ends)
    np.testing.assert_array_equal(feature.geometry.parts, fgb_multipolygon.parts)
    np.testing.assert_array_almost_equal(
        feature.geometry.coords, fgb_multipolygon.coords
    )


def test_fgb_property_types(tmp_path: Path):
    # One column per supported attribute type
    path = Path(tmp_path, "properties.fgb")
    col_names = [
        "byte", "ubyte", "flag", "short", "ushort", "int", "uint", "long",
        "ulong", "float", "double", "string", "json", "datetime", "binary",
    ]  # fmt: skip
    col_types = [
        CT_BYTE, CT_UBYTE, CT_BOOL, CT_SHORT, CT_USHORT, CT_INT, CT_UINT,
        CT_LONG, CT_ULONG, CT_FLOAT, CT_DOUBLE, CT_STRING, CT_JSON,
        CT_DATETIME, CT_BINARY,
    ]  # fmt: skip
    values = [
        -5, 250, True, -1234, 65000, -123456, 4_000_000_000,
        -1_234_567_890_123, 1_234_567_890_123, 1.25, 2.5, "plain",
        '{"ok": true}', "2026-10-02T11:54:31", b"\x00\x01abc",
    ]  # fmt: skip
    geom = make_geometry(GT_POINT, [9.0, 8.0])
    writer = FlatGeobufWriter(
        path.as_posix(),
        col_names=col_names,
        col_types=col_types,
        geom_type=GT_POINT,
        name="properties",
    )
    writer.add_feature(geom.xy, values=values)
    writer.finalize()

    # Read the single feature back
    feature = next(iter(FlatGeobufReader(path.as_posix())))

    # Assert the integer, float and trailing values survived
    assert feature.values[:9] == values[:9]
    assert feature.get_field("float") == pytest.approx(1.25)
    assert feature.get_field("double") == pytest.approx(2.5)
    assert feature.values[11:] == values[11:]
