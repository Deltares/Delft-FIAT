from pathlib import Path
from types import SimpleNamespace

import pytest

from fiat.driver import FlatGeobufDriver, NetcdfDriver, fgb
from fiat.open import open_geom, open_grid


## Datasets
# Made for testing in this module, copy exists in main conftest
@pytest.fixture
def exposure_geom_repr(exposure_geom_path: Path) -> FlatGeobufDriver:
    ds = open_geom(exposure_geom_path)  # Read only
    assert isinstance(ds, FlatGeobufDriver)
    return ds


@pytest.fixture
def hazard_event_repr(hazard_event_path: Path) -> NetcdfDriver:
    ds = open_grid(hazard_event_path)  # Read only
    assert isinstance(ds, NetcdfDriver)
    return ds


## GIS related objects
# Other
@pytest.fixture(scope="session")
def geotransform() -> tuple:
    gtf = (0, 0.5, 0.0, 10, 0.0, -0.5)
    return gtf


def _feature(geom) -> SimpleNamespace:
    """Wrap a geometry in a minimal feature-like object."""
    return SimpleNamespace(geometry=geom)


# Features (as GDAL-free geometries / feature-likes)
@pytest.fixture(scope="session")
def feature_linestring() -> SimpleNamespace:
    # LINESTRING (1.5 1.5, 2.5 1.5, 3.5 2.5, 4.5 2.5)
    xy = [1.5, 1.5, 2.5, 1.5, 3.5, 2.5, 4.5, 2.5]
    return _feature(fgb.make_geometry(fgb.GT_LINESTRING, xy))


@pytest.fixture
def feature_point() -> SimpleNamespace:
    return _feature(fgb.make_geometry(fgb.GT_POINT, [1.5, 1.5]))


@pytest.fixture
def feature_polygon() -> SimpleNamespace:
    # POLYGON ((1.5 2.5, 2.5 2.5, 2.5 1.5, 1.5 1.5, 1.5 2.5))
    xy = [1.5, 2.5, 2.5, 2.5, 2.5, 1.5, 1.5, 1.5, 1.5, 2.5]
    return _feature(fgb.make_geometry(fgb.GT_POLYGON, xy, ends=[5]))


@pytest.fixture(scope="session")
def feature_polygon_complex() -> SimpleNamespace:
    # POLYGON ((4.5 5.5, 4.5 2.5, 6.5 2.5, 6.5 3.5, 5.5 3.5, 5.5 5.5, 4.5 5.5))
    xy = [4.5, 5.5, 4.5, 2.5, 6.5, 2.5, 6.5, 3.5, 5.5, 3.5, 5.5, 5.5, 4.5, 5.5]
    return _feature(fgb.make_geometry(fgb.GT_POLYGON, xy, ends=[7]))
