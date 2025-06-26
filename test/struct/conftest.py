from pathlib import Path

import numpy as np
import pytest
from osgeo import ogr, osr

from fiat.fio import GeomIO, GridIO, open_geom, open_grid
from fiat.fio.handler import BufferHandler
from fiat.fio.parser import CSVParser


## I/O structures needed for this testing
@pytest.fixture
def exposure_geom_write(srs: osr.SpatialReference) -> GeomIO:
    ds = open_geom("tmp", mode="w")  # Write only
    assert isinstance(ds, GeomIO)
    ds.create_layer(srs, 1)
    return ds


@pytest.fixture
def hazard_write(srs: osr.SpatialReference) -> GridIO:
    ds = open_grid("tmp", mode="w")  # Write only
    assert isinstance(ds, GridIO)
    ds.create(shape=(2, 3), nb=1, type=6)  # 6 = float32
    ds.set_source_srs(srs)
    return ds


@pytest.fixture
def feature(exposure_geom_write: GeomIO) -> ogr.Feature:
    geom = ogr.Geometry(ogr.wkbPoint)
    geom.AddPoint_2D(1, 1)
    ft = ogr.Feature(exposure_geom_write.layer.defn)
    ft.SetGeometry(geom)
    ft.SetFID(1)
    return ft


@pytest.fixture
def exposure_data_parsed(exposure_data_path: Path) -> CSVParser:
    bh = BufferHandler(exposure_data_path)
    p = CSVParser(bh, delimiter=",", header=True)
    return p


@pytest.fixture(scope="session")
def table_array() -> np.ndarray:
    data = np.array([[1, 3], [2, 4]])
    return data
