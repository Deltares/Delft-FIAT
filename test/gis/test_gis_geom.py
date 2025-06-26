from pathlib import Path

import numpy as np
from osgeo import ogr

from fiat.fio import GeomIO
from fiat.gis.geom import point_in_geom, reproject, reproject_feature
from fiat.util import get_srs_repr


def test_point_in_geom_linestring(feature_linestring: ogr.Feature):
    # Call the function
    p = point_in_geom(feature_linestring)

    # Assert the output
    assert p == (3, 2)


def test_point_in_geom_point(feature_point: ogr.Feature):
    # Call the function
    p = point_in_geom(feature_point)

    # Assert the output
    assert p == (1.5, 1.5)


def test_point_in_geom_polygon(feature_polygon: ogr.Feature):
    # Call the function
    p = point_in_geom(feature_polygon)

    # Assert the output
    assert p == (1.5, 1.5)


def test_reproject_feature_point(feature_point: ogr.Feature):
    # Assert current state
    geom = feature_point.GetGeometryRef()
    assert geom.GetPoint_2D() == (1.5, 1.5)

    # Call the function
    geom = reproject_feature(geom, src_srs="EPSG:4326", dst_srs="EPSG:3857")
    # Assert the output
    np.testing.assert_array_almost_equal(
        geom.GetPoint_2D(),
        (166979.23618991036, 166998.31375292226),
    )


def test_reproject_feature_polygon(feature_polygon: ogr.Feature):
    # Assert current state
    geom = feature_polygon.GetGeometryRef()
    assert geom.GetGeometryRef(0).GetPoint_2D(0) == (1.0, 2.0)  # Due to interior

    # Call the function
    geom = reproject_feature(geom, src_srs="EPSG:4326", dst_srs="EPSG:3857")
    # Assert the output
    np.testing.assert_array_almost_equal(
        geom.GetGeometryRef(0).GetPoint_2D(0),
        (111319.490793, 222684.208506),
    )


def test_reproject(
    tmp_path: Path,
    exposure_geom_repr: GeomIO,
):
    # Assert the current state
    assert get_srs_repr(exposure_geom_repr.srs) == "EPSG:4326"
    ft = exposure_geom_repr.layer[0]
    geom = ft.GetGeometryRef()
    assert geom.GetGeometryRef(0).GetPoint_2D(0) == (0.5, 9.5)

    # Call the function
    gs = reproject(exposure_geom_repr, srs="EPSG:3857", out_dir=tmp_path)

    # Assert the output
    assert Path(tmp_path, "spatial_repr.geojson").is_file()
    assert get_srs_repr(gs.srs) == "EPSG:3857"
    ft = gs.layer[0]
    geom = ft.GetGeometryRef()
    assert geom.GetGeometryRef(0).GetPoint_2D(0) == (
        55659.74539663678,
        1062414.3112675361,
    )
