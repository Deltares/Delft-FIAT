from pathlib import Path

import pytest
from osgeo import gdal, ogr, osr

from fiat.fio import GeomIO, GridIO, open_geom, open_grid


## Datasets
# Made for testing in this module, copy exists in main conftest
@pytest.fixture
def exposure_geom_repr(exposure_geom_path: Path) -> GeomIO:
    ds = open_geom(exposure_geom_path)  # Read only
    assert isinstance(ds, GeomIO)
    return ds


@pytest.fixture
def hazard_event_repr(hazard_event_path: Path) -> GridIO:
    ds = open_grid(hazard_event_path)  # Read only
    assert isinstance(ds, GridIO)
    return ds


@pytest.fixture
def hazard_tif(tmp_path: Path, srs: osr.SpatialReference) -> GridIO:
    ds = open_grid(Path(tmp_path, "tmp.tif"), "w")
    ds.create(shape=(10, 10), nb=1, type=gdal.GDT_Float32)
    ds.set_source_srs(srs)
    ds.geotransform = (0.0, 1.0, 0.0, 10.0, 0.0, -1.0)
    ds.close()
    return ds.reopen()


## GIS related objects
# Layers
@pytest.fixture(scope="session")
def linestring_defn() -> ogr.FeatureDefn:
    defn = ogr.FeatureDefn()
    defn.SetGeomType(ogr.wkbLineString)
    return defn


@pytest.fixture(scope="session")
def point_defn() -> ogr.FeatureDefn:
    defn = ogr.FeatureDefn()
    defn.SetGeomType(ogr.wkbPoint)
    return defn


@pytest.fixture(scope="session")
def polygon_defn() -> ogr.FeatureDefn:
    defn = ogr.FeatureDefn()
    defn.SetGeomType(ogr.wkbPolygon)
    return defn


# Features
@pytest.fixture(scope="session")
def feature_linestring(linestring_defn: ogr.FeatureDefn) -> ogr.Feature:
    wkt = "LINESTRING (1 1, 2 1, 3 2, 4 2)"
    geom = ogr.CreateGeometryFromWkt(wkt)
    ft = ogr.Feature(linestring_defn)
    ft.SetFID(1)
    ft.SetGeometry(geom)
    return ft


@pytest.fixture
def feature_point(point_defn: ogr.FeatureDefn) -> ogr.Feature:
    ft = ogr.Feature(point_defn)
    geom = ogr.Geometry(ogr.wkbPoint)
    geom.AddPoint_2D(1.5, 1.5)
    ft.SetFID(1)
    ft.SetGeometry(geom)
    return ft


@pytest.fixture(scope="session")
def feature_polygon(polygon_defn: ogr.FeatureDefn) -> ogr.Feature:
    wkt = "POLYGON ((1 2, 2 2, 2 1, 1 1, 1 2))"
    geom = ogr.CreateGeometryFromWkt(wkt)
    ft = ogr.Feature(polygon_defn)
    ft.SetFID(1)
    ft.SetGeometry(geom)
    return ft
