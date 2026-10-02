from fiat.gis import _geom


def test_point_in_geometry(exposure_feature_geom):
    # A point clearly inside the exposure polygon
    assert _geom.point_in_geometry(exposure_feature_geom, 1.0, 9.0)


def test_point_in_geometry_outside(exposure_feature_geom):
    # A point clearly outside the exposure polygon
    assert not _geom.point_in_geometry(exposure_feature_geom, 3.0, 9.0)


def test_point_in_geometry_hole(feature_polygon_hole):
    # Set the geometry
    geom = feature_polygon_hole.geometry

    # A point in the hole is outside, one in the ring body is inside
    assert not _geom.point_in_geometry(geom, 2.0, 2.0)  # Inside the hole
    assert _geom.point_in_geometry(geom, 0.5, 0.5)  # In the body


def test_point_in_geometry_multipolygon(feature_multipolygon):
    # Set the geometry
    geom = feature_multipolygon.geometry

    # A point in either part is inside, the gap between them is outside
    assert _geom.point_in_geometry(geom, 0.5, 0.5)  # First part
    assert _geom.point_in_geometry(geom, 2.5, 2.5)  # Second part
    assert not _geom.point_in_geometry(geom, 1.5, 1.5)  # Between parts


def test_intersect_cell(exposure_feature_geom):
    # A cell overlapping the exposure polygon
    assert _geom.intersect_cell(exposure_feature_geom, x=1.0, y=9.0, dx=0.25, dy=-0.25)


def test_intersect_cell_outside(exposure_feature_geom):
    # A cell outside the geometry envelope is rejected early
    assert not _geom.intersect_cell(
        exposure_feature_geom, x=10.0, y=10.0, dx=1.0, dy=-1.0
    )


def test_intersect_cell_point(feature_point):
    # A cell containing the point
    assert _geom.intersect_cell(feature_point.geometry, x=1.0, y=1.0, dx=1.0, dy=1.0)


def test_intersect_cell_multipoint(feature_multipoint):
    # Set the geometry
    geom = feature_multipoint.geometry

    # A cell around one of the points hits, one around the gap misses
    assert _geom.intersect_cell(geom, x=1.5, y=1.5, dx=1.0, dy=1.0)
    assert not _geom.intersect_cell(geom, x=0.5, y=0.5, dx=1.0, dy=1.0)


def test_intersect_cell_line(feature_linestring):
    # A cell the line crosses diagonally
    assert _geom.intersect_cell(
        feature_linestring.geometry, x=2.0, y=1.0, dx=1.0, dy=1.0
    )


def test_intersect_cell_multiline(feature_multilinestring):
    # Set the geometry
    geom = feature_multilinestring.geometry

    # A cell on the first part hits, one in the gap between parts misses
    assert _geom.intersect_cell(geom, x=0.25, y=-0.25, dx=0.5, dy=0.5)
    assert not _geom.intersect_cell(geom, x=1.5, y=-0.25, dx=1.0, dy=0.5)


def test_intersect_cell_covered(feature_polygon_hole):
    # An interior cell is covered even without a vertex or edge in it
    assert _geom.intersect_cell(
        feature_polygon_hole.geometry, x=0.25, y=0.25, dx=0.5, dy=0.5
    )


def test_point_on_surface(exposure_feature_geom):
    # The representative point lies inside the polygon
    point = _geom.point_on_surface(exposure_feature_geom)
    assert _geom.point_in_geometry(exposure_feature_geom, *point)


def test_point_on_surface_point(feature_point):
    # A point geometry returns its own coordinate
    assert _geom.point_on_surface(feature_point.geometry) == (1.5, 1.5)


def test_point_on_surface_multipoint(feature_multipoint):
    # A multipoint returns its first coordinate
    assert _geom.point_on_surface(feature_multipoint.geometry) == (0.0, 0.0)


def test_point_on_surface_line(feature_linestring):
    # A line returns its middle vertex
    assert _geom.point_on_surface(feature_linestring.geometry) == (3.5, 2.5)


def test_point_on_surface_concave(feature_polygon_concave):
    # Set the geometry, the centroid falls outside the shape
    geom = feature_polygon_concave.geometry

    # The scanline fallback yields a point that is actually inside
    point = _geom.point_on_surface(geom)
    assert _geom.point_in_geometry(geom, *point)


def test_point_on_surface_hole(feature_polygon_hole):
    # Set the geometry
    geom = feature_polygon_hole.geometry

    # The representative point avoids the hole
    point = _geom.point_on_surface(geom)
    assert _geom.point_in_geometry(geom, *point)
    assert not _geom.point_in_geometry(geom, 2.0, 2.0)
