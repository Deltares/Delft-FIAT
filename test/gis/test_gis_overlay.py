import numpy as np
from osgeo import ogr

from fiat.fio import GridIO
from fiat.gis.overlay import (
    area_mask,
    centroid_mask,
    clip,
    clip_weighted,
    intersect_cell,
    point_mask,
)


def test_area_mask_linestring(
    feature_linestring: ogr.Feature,
    hazard_event_data: GridIO,
):
    # Call the function
    m, w = area_mask(
        geom=feature_linestring.GetGeometryRef(),
        gtf=hazard_event_data.geotransform,
        shape=hazard_event_data.shape_xy,
    )

    # Assert the output
    assert m.shape == (2, 4)
    assert np.sum(m) == 6
    assert m[0, 0] == 0
    assert m[1, 3] == 0
    assert isinstance(w, tuple)
    assert w == (1, 7, 4, 2)


def test_area_mask_polygon(
    feature_polygon: ogr.Feature,
    hazard_event_data: GridIO,
):
    # Call the function
    m, w = area_mask(
        geom=feature_polygon.GetGeometryRef(),
        gtf=hazard_event_data.geotransform,
        shape=hazard_event_data.shape_xy,
    )

    # Assert the output
    assert m.shape == (2, 2)
    assert np.sum(m) == 4
    assert isinstance(w, tuple)
    assert w == (1, 7, 2, 2)


def test_area_mask_polygon_complex(
    feature_polygon_complex: ogr.Feature,
    hazard_event_data: GridIO,
):
    # Call the function
    m, w = area_mask(
        geom=feature_polygon_complex.GetGeometryRef(),
        gtf=hazard_event_data.geotransform,
        shape=hazard_event_data.shape_xy,
    )

    # Assert the output
    assert m.shape == (4, 3)
    assert np.sum(m) == 10
    assert m[0, 2] == 0
    assert m[1, 2] == 0
    assert isinstance(w, tuple)
    assert w == (4, 4, 3, 4)


def test_point_mask(
    feature_point: ogr.Feature,
    hazard_event_data: GridIO,
):
    # Call the function
    geom = feature_point.GetGeometryRef()
    m, w = point_mask(
        point=geom.GetPoint_2D(),
        gtf=hazard_event_data.geotransform,
        shape=hazard_event_data.shape_xy,
    )

    # Assert the output
    np.testing.assert_array_equal(m, [[1]])
    np.testing.assert_array_equal(w, [1, 8, 1, 1])


def test_centroid_mask(
    feature_polygon: ogr.Feature,
    hazard_event_data: GridIO,
):
    # Call the function
    geom = feature_polygon.GetGeometryRef()
    m, w = centroid_mask(
        geom=geom,
        gtf=hazard_event_data.geotransform,
        shape=hazard_event_data.shape_xy,
    )

    # Assert the output
    np.testing.assert_array_equal(m, [[1]])
    np.testing.assert_array_equal(w, [2, 8, 1, 1])


def test_clip_linestring(
    feature_linestring: ogr.Feature,
    hazard_event_data: GridIO,
):
    # Mask first
    m, w = area_mask(
        geom=feature_linestring.GetGeometryRef(),
        gtf=hazard_event_data.geotransform,
        shape=hazard_event_data.shape_xy,
    )

    # Call the function
    c = clip(
        band=hazard_event_data[0],
        mask=m,
        window=w,
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
    # Mask first
    m, w = area_mask(
        geom=feature_polygon.GetGeometryRef(),
        gtf=hazard_event_data.geotransform,
        shape=hazard_event_data.shape_xy,
    )

    # Call the function
    c = clip(
        band=hazard_event_data[0],
        mask=m,
        window=w,
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
    # Mask first
    m, w = area_mask(
        geom=feature_polygon_complex.GetGeometryRef(),
        gtf=hazard_event_data.geotransform,
        shape=hazard_event_data.shape_xy,
    )

    # Call the function
    c = clip(
        band=hazard_event_data[0],
        mask=m,
        window=w,
    )

    # Assert the output
    np.testing.assert_array_almost_equal(
        c,
        [2.0, 1.8, 1.8, 1.6, 1.6, 1.4, 1.2, 1.4, 1.2, 1.0],
    )


def test_clip_point(
    feature_point: ogr.Feature,
    hazard_event_data: GridIO,
):
    # Mask First
    geom = feature_point.GetGeometryRef()
    m, w = point_mask(
        point=geom.GetPoint_2D(),
        gtf=hazard_event_data.geotransform,
        shape=hazard_event_data.shape_xy,
    )

    # Call the function
    c = clip(
        band=hazard_event_data[0],
        mask=m,
        window=w,
    )

    # Assert the output
    np.testing.assert_array_almost_equal(c, [1.8])


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
