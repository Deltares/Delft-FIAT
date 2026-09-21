import shutil
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from osgeo import ogr, osr

from fiat.driver.csv import CSVParser
from fiat.driver.geom import GeomDriver
from fiat.driver.handler import BufferHandler, FileBufferHandler
from fiat.driver.netcdf import NetcdfDriver
from fiat.open import open_geom, open_grid


## Paths to data and temporary data
@pytest.fixture
def exposure_geom_empty_tmp_path(tmp_path: Path, exposure_geom_data: Path) -> Path:
    p = Path(tmp_path, "tmp.geojson")
    with open_geom(p, mode="w") as writer:
        writer.create_layer(
            exposure_geom_data.layer.crs,
            exposure_geom_data.layer.geom_type,
        )
        writer.layer.set_from_defn(exposure_geom_data.layer.defn)
    assert p.is_file()
    return p


@pytest.fixture(scope="session")
def exposure_geom_no_crs_path(testdata_dir: Path):
    p = Path(testdata_dir, "exposure", "spatial_no_crs.fgb")
    assert p.is_file()
    return p


@pytest.fixture(scope="session")
def hazard_event_no_crs_path(testdata_dir: Path):
    p = Path(testdata_dir, "event_map_no_crs.nc")
    assert p.is_file()
    return p


@pytest.fixture
def hazard_event_tmp_path(tmp_path: Path, hazard_event_path: Path) -> Path:
    p = Path(tmp_path, "tmp.nc")
    shutil.copy2(hazard_event_path, p)
    assert p.is_file()
    return p


## Objects/ data structures
@pytest.fixture
def buffer() -> BytesIO:
    b = BytesIO()
    b.write(
        b"""#dtypes=str,int,int
index,val1,val2
fp1,1,2
fp2,3,4
"""
    )
    b.seek(0)
    return b


@pytest.fixture
def buffer_handler(buffer: BytesIO) -> BufferHandler:
    h = BufferHandler(buffer)
    h.nchar = b"\n"
    h.size = h.stream.read().count(h.nchar)
    return h


@pytest.fixture(scope="session")
def file_buffer_handler(vulnerability_path: Path) -> FileBufferHandler:
    h = FileBufferHandler(vulnerability_path)
    return h


@pytest.fixture(scope="session")
def vulnerability_win_path(testdata_dir: Path) -> Path:
    p = Path(testdata_dir, "vulnerability", "curves_win.csv")
    assert p.is_file()
    return p


## I/O structures needed for this testing
@pytest.fixture
def exposure_geom_write(crs_4326: osr.SpatialReference) -> GeomDriver:
    ds = open_geom("tmp", mode="w")  # Write only
    assert isinstance(ds, GeomDriver)
    ds.create_layer(crs_4326, 1)
    return ds


@pytest.fixture
def hazard_write(crs_4326: osr.SpatialReference) -> NetcdfDriver:
    ds = open_grid("tmp", mode="w")  # Write only
    assert isinstance(ds, NetcdfDriver)
    ds.create(shape=(2, 3), nb=1, dtype=6)  # 6 = float32
    ds.set_source_crs(crs_4326)
    return ds


@pytest.fixture
def feature(exposure_geom_write: GeomDriver) -> ogr.Feature:
    geom = ogr.Geometry(ogr.wkbPoint)
    geom.AddPoint_2D(1, 1)
    ft = ogr.Feature(exposure_geom_write.layer.defn)
    ft.SetGeometry(geom)
    ft.SetFID(1)
    return ft


@pytest.fixture(scope="session")
def table_array() -> np.ndarray:
    data = np.array([[1, 3], [2, 4]])
    return data


@pytest.fixture
def vulnerability_parsed(vulnerability_path: Path) -> CSVParser:
    bh = FileBufferHandler(vulnerability_path)
    p = CSVParser(bh, delimiter=",", header=True)
    return p
