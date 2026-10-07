import pickle
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
    FlatGeobufReader,
    FlatGeobufWriter,
    Geometry,
    VectorProfile,
    make_geometry,
)
from fiat.util import get_crs_repr


def _square(minx: float, miny: float, maxx: float, maxy: float) -> Geometry:
    """Build a closed square polygon geometry."""
    xy = [minx, miny, maxx, miny, maxx, maxy, minx, maxy, minx, miny]
    return make_geometry(GT_POLYGON, xy, ends=[5])


def _write_layer(path: Path) -> FlatGeobufWriter:
    """Write a small two-feature polygon layer and return the (closed) writer."""
    crs = CRS.from_epsg(4326)
    geometries = [_square(0.0, 0.0, 1.0, 1.0), _square(2.0, 2.0, 3.0, 4.0)]
    values = [[1, 2.5, "one"], [2, 5.0, "two"]]
    writer = FlatGeobufWriter(
        path.as_posix(),
        col_names=["object_id", "score", "name"],
        col_types=[CT_INT, CT_DOUBLE, CT_STRING],
        geom_type=GT_POLYGON,
        name="layer",
        crs_wkt=crs.to_wkt(),
        crs_org="EPSG",
        crs_code=4326,
    )
    for geom, row in zip(geometries, values):
        writer.add_feature(geom.xy, geom.ends, geom.parts, row)
    writer.finalize()
    return writer


## Writing
def test_fgb_write(tmp_path: Path):
    # Write a small layer to disk
    path = Path(tmp_path, "write.fgb")
    writer = _write_layer(path)

    # The file was created and the writer exposes its own profile
    assert path.is_file()
    assert writer.profile.name == "layer"
    assert writer.profile.geom_type == GT_POLYGON
    assert writer.profile.fields == ["object_id", "score", "name"]
    assert writer.profile.dtypes == [CT_INT, CT_DOUBLE, CT_STRING]
    assert get_crs_repr(writer.profile.crs) == "EPSG:4326"

    # One index record per written feature
    assert len(writer.records) == 2


def test_fgb_write_property_types(tmp_path: Path):
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


## Reading
def test_fgb_read_metadata(exposure_geom_data: FlatGeobufReader):
    # The reader exposes the header metadata
    reader = exposure_geom_data
    assert reader.name == "spatial"
    assert len(reader) == 4
    assert reader.geometry_type == GT_POLYGON
    assert reader.crs_org == "EPSG"
    assert reader.crs_code == 4326


def test_fgb_read_profile(exposure_geom_data: FlatGeobufReader):
    # The shared vector profile carries the layer metadata
    profile = exposure_geom_data.profile
    assert isinstance(profile, VectorProfile)
    assert profile.name == "spatial"
    assert profile.size == 4
    assert profile.geom_type == GT_POLYGON

    # Field schema
    assert profile.fields[:2] == ["object_id", "object_name"]
    assert len(profile.fields) == 5
    # FlatGeobuf ColumnType codes: 5 = Int, 11 = String
    assert profile.dtypes[:2] == [5, 11]
    assert list(profile.columns)[:2] == ["object_id", "object_name"]
    assert profile.columns["object_id"] == 0

    # Spatial metadata
    np.testing.assert_array_almost_equal(
        profile.bounds,
        (0.5, 1.05, 8.95, 9.5),
    )
    assert get_crs_repr(profile.crs) == "EPSG:4326"


def test_fgb_read_features(exposure_geom_data: FlatGeobufReader):
    # Iterate over the layer
    features = list(exposure_geom_data)

    # Assert the output
    assert len(features) == exposure_geom_data.profile.size
    assert all(isinstance(ft, Feature) for ft in features)


def test_fgb_feature_get_field(exposure_geom_data: FlatGeobufReader):
    # Retrieve a feature
    ft = next(iter(exposure_geom_data))

    # Access fields by index and by name
    assert ft.get_field(0) == ft.get_field("object_id")
    assert isinstance(ft.get_field("object_name"), str)
    assert ft[0] == ft.get_field(0)


## Selecting / windowing
def test_fgb_select_bbox(exposure_geom_data: FlatGeobufReader):
    # Select features intersecting a bounding box using the R-tree index
    feats = list(exposure_geom_data.select(0.0, 8.0, 2.0, 10.0))

    # Only the top-left polygon (object_id 1) is inside
    assert len(feats) == 1
    assert feats[0].get_field("object_id") == 1


def test_fgb_select_bbox_empty(exposure_geom_data: FlatGeobufReader):
    # A bounding box outside the data returns nothing
    feats = list(exposure_geom_data.select(100.0, 100.0, 200.0, 200.0))
    assert feats == []


def test_fgb_reduced_iter(exposure_geom_data: FlatGeobufReader):
    # Iterate over a 1-based inclusive slice of the features
    feats = list(exposure_geom_data.reduced_iter(1, 2))

    # Assert the output
    assert len(feats) == 2
    assert all(isinstance(ft, Feature) for ft in feats)


## CRS handling
def test_fgb_crs_from_file(exposure_geom_path: Path):
    # The CRS is induced from the file header
    reader = FlatGeobufReader(exposure_geom_path.as_posix())
    assert isinstance(reader.profile.crs, CRS)
    assert get_crs_repr(reader.profile.crs) == "EPSG:4326"


def test_fgb_crs_override(exposure_geom_no_crs_path: Path, crs_4326: CRS):
    # A file without a CRS resolves to None
    reader = FlatGeobufReader(exposure_geom_no_crs_path.as_posix())
    assert reader.profile.size == 4
    assert reader.profile.crs is None

    # A user-provided CRS is used only when the file carries none
    reader = FlatGeobufReader(
        exposure_geom_no_crs_path.as_posix(),
        crs="EPSG:4326",
    )
    assert isinstance(reader.profile.crs, CRS)
    assert get_crs_repr(reader.profile.crs) == "EPSG:4326"


## Lifecycle
def test_fgb_pickle(exposure_geom_path: Path):
    # Pickling should round-trip via __reduce__ (reopen by path)
    reader = FlatGeobufReader(exposure_geom_path.as_posix())
    reader2 = pickle.loads(pickle.dumps(reader))

    # Assert the reconstructed reader works
    assert isinstance(reader2, FlatGeobufReader)
    assert reader2.path == reader.path
    assert reader2.profile.size == 4


def test_fgb_close_context(exposure_geom_path: Path):
    # The reader works as a context manager and tracks its closed state
    with FlatGeobufReader(exposure_geom_path.as_posix()) as reader:
        assert reader.closed is False
        assert reader.profile.size == 4
    assert reader.closed is True


## Geometry fidelity (round trips)
def _roundtrip(path: Path, geom: Geometry) -> Feature:
    """Write a single feature and return the feature read back."""
    writer = FlatGeobufWriter(
        path.as_posix(),
        col_names=["object_id", "name"],
        col_types=[CT_INT, CT_STRING],
        geom_type=geom.type,
        name=path.stem,
    )
    writer.add_feature(geom.xy, geom.ends, geom.parts, [7, path.stem])
    writer.finalize()
    return next(iter(FlatGeobufReader(path.as_posix())))


def test_fgb_roundtrip_point(tmp_path: Path, fgb_point: Geometry):
    feature = _roundtrip(Path(tmp_path, "point.fgb"), fgb_point)
    assert feature.geometry.type == fgb_point.type
    assert feature.geometry.envelope() == fgb_point.envelope()
    np.testing.assert_array_almost_equal(feature.geometry.coords, fgb_point.coords)


def test_fgb_roundtrip_multipoint(tmp_path: Path, fgb_multipoint: Geometry):
    feature = _roundtrip(Path(tmp_path, "multipoint.fgb"), fgb_multipoint)
    assert feature.geometry.type == fgb_multipoint.type
    np.testing.assert_array_almost_equal(feature.geometry.coords, fgb_multipoint.coords)


def test_fgb_roundtrip_linestring(tmp_path: Path, fgb_linestring: Geometry):
    feature = _roundtrip(Path(tmp_path, "linestring.fgb"), fgb_linestring)
    assert feature.geometry.type == fgb_linestring.type
    np.testing.assert_array_almost_equal(feature.geometry.coords, fgb_linestring.coords)


def test_fgb_roundtrip_multilinestring(tmp_path: Path, fgb_multilinestring: Geometry):
    feature = _roundtrip(Path(tmp_path, "multilinestring.fgb"), fgb_multilinestring)
    assert feature.geometry.type == fgb_multilinestring.type
    np.testing.assert_array_equal(feature.geometry.ends, fgb_multilinestring.ends)
    np.testing.assert_array_almost_equal(
        feature.geometry.coords, fgb_multilinestring.coords
    )


def test_fgb_roundtrip_polygon_hole(tmp_path: Path, fgb_polygon_hole: Geometry):
    feature = _roundtrip(Path(tmp_path, "polygon_hole.fgb"), fgb_polygon_hole)
    assert feature.geometry.type == fgb_polygon_hole.type
    np.testing.assert_array_equal(feature.geometry.ends, fgb_polygon_hole.ends)
    np.testing.assert_array_almost_equal(
        feature.geometry.coords, fgb_polygon_hole.coords
    )


def test_fgb_roundtrip_multipolygon(tmp_path: Path, fgb_multipolygon: Geometry):
    feature = _roundtrip(Path(tmp_path, "multipolygon.fgb"), fgb_multipolygon)
    assert feature.geometry.type == fgb_multipolygon.type
    np.testing.assert_array_equal(feature.geometry.ends, fgb_multipolygon.ends)
    np.testing.assert_array_equal(feature.geometry.parts, fgb_multipolygon.parts)
    np.testing.assert_array_almost_equal(
        feature.geometry.coords, fgb_multipolygon.coords
    )
