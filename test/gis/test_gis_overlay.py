import numpy as np
from osgeo import ogr

from fiat.fio import GridIO
from fiat.gis.overlay import clip, clip_weighted, intersect_cell, pin


def test_clip_linestring(
    feature_linestring: ogr.Feature,
    hazard_event_data: GridIO,
):
    # Call the function
    c = clip(
        ft=feature_linestring,
        band=hazard_event_data[0],
        gtf=hazard_event_data.geotransform,
    )

    # Assert the output
    np.testing.assert_array_almost_equal(
        c,
        [1.8, 1.6, 1.4, 1.8, 1.6, 1.4],
    )


def test_clip_polygon(
    feature_polygon: ogr.Feature,
    hazard_event_data: GridIO,
):
    # Call the function
    c = clip(
        ft=feature_polygon,
        band=hazard_event_data[0],
        gtf=hazard_event_data.geotransform,
    )

    # Assert the output
    np.testing.assert_array_almost_equal(
        c,
        [2.0, 1.8, 1.8, 1.6],
    )


def test_clip_polygon_complex(
    feature_polygon_complex: ogr.Feature,
    hazard_event_data: GridIO,
):
    # Call the function
    c = clip(
        ft=feature_polygon_complex,
        band=hazard_event_data[0],
        gtf=hazard_event_data.geotransform,
    )

    # Assert the output
    np.testing.assert_array_almost_equal(
        c,
        [2.0, 1.8, 1.8, 1.6, 1.6, 1.4, 1.2, 1.4, 1.2, 1.0],
    )


def test_clip_weighted_3(
    feature_polygon: ogr.Feature,
    hazard_event_data: GridIO,
):
    # Call the function
    c, m = clip_weighted(
        ft=feature_polygon,
        band=hazard_event_data[0],
        gtf=hazard_event_data.geotransform,
        upscale=3,
    )

    # Assert the output
    np.testing.assert_array_almost_equal(
        c,
        [2.0, 1.8, 1.8, 1.6],
    )
    # As a result of a square in the middle and upscaling a 2x2 3 times
    # 4 out of 9 cells are covered when upscaled, so 0.4444444
    np.testing.assert_array_almost_equal(
        m,
        [[0.44, 0.44], [0.44, 0.44]],
        decimal=2,
    )


def test_intersect_cell_true(feature_polygon: ogr.Feature):
    # Call the function
    b = intersect_cell(
        geom=feature_polygon.GetGeometryRef(),
        x=1,
        y=2,
        dx=1,
        dy=-1,
    )

    # Assert the output
    assert b


def test_intersect_cell_false(feature_polygon: ogr.Feature):
    # Call the function
    b = intersect_cell(
        geom=feature_polygon.GetGeometryRef(),
        x=1,
        y=4,  # End just above the polygon this way
        dx=1,
        dy=-1,
    )

    # Assert the output
    assert not b


def test_pin(
    feature_point: ogr.Feature,
    hazard_event_data: GridIO,
):
    # Call the function
    geom = feature_point.GetGeometryRef()
    v = pin(
        point=geom.GetPoint_2D(),
        band=hazard_event_data[0],
        gtf=hazard_event_data.geotransform,
    )

    # Assert the output
    np.testing.assert_array_almost_equal(v, [1.8])
