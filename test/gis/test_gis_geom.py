from pathlib import Path

import numpy as np
from pyproj import Transformer

from fiat.driver import FlatGeobufReader
from fiat.gis.geom import point_in_geom, reproject, reproject_feature
from fiat.util import get_crs_repr


def test_point_in_geom_linestring(feature_linestring):
    # Call the function
    p = point_in_geom(feature_linestring.geometry)

    # Assert the output
    assert p == (3.5, 2.5)


def test_point_in_geom_point(feature_point):
    # Call the function
    p = point_in_geom(feature_point.geometry)

    # Assert the output
    assert p == (1.5, 1.5)


def test_point_in_geom_polygon(feature_polygon):
    # Call the function
    p = point_in_geom(feature_polygon.geometry)

    # Assert the output
    assert p == (2.0, 2.0)


def test_reproject_feature_point(feature_point):
    # Assert current state
    geom = feature_point.geometry
    assert tuple(geom.coords[0]) == (1.5, 1.5)

    # Call the function
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    xy, _, _ = reproject_feature(geom, transformer)

    # Assert the output
    np.testing.assert_array_almost_equal(
        xy[:2],
        (166979.23618991036, 166998.31375292226),
    )


def test_reproject_feature_polygon(feature_polygon):
    # Assert current state
    geom = feature_polygon.geometry
    assert tuple(geom.coords[0]) == (1.5, 2.5)  # Due to interior

    # Call the function
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    xy, _, _ = reproject_feature(geom, transformer)

    # Assert the output
    np.testing.assert_array_almost_equal(
        xy[:2],
        (166979.23619, 278387.075954),
    )


def _feature_by_id(layer, object_id):
    """Return the feature with a given object_id (order-independent)."""
    for ft in layer:
        if ft.get_field("object_id") == object_id:
            return ft
    raise AssertionError(f"No feature with object_id={object_id}")


def test_reproject(
    tmp_path: Path,
    exposure_geom_repr: FlatGeobufReader,
):
    # Assert the current state
    assert get_crs_repr(exposure_geom_repr.profile.crs) == "EPSG:4326"
    ft = _feature_by_id(exposure_geom_repr, 1)
    assert tuple(ft.geometry.coords[0]) == (0.5, 9.5)

    # Call the function
    ds = reproject(exposure_geom_repr, dst_crs="EPSG:3857", output_dir=tmp_path)

    # Assert the output
    assert Path(tmp_path, "spatial_repr.fgb").is_file()
    assert get_crs_repr(ds.profile.crs) == "EPSG:3857"
    ft = _feature_by_id(ds, 1)
    np.testing.assert_array_almost_equal(
        tuple(ft.geometry.coords[0]),
        (55659.74539663678, 1062414.3112675361),
    )
