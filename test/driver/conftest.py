import shutil
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest

from fiat.driver import fgb
from fiat.driver.csv import parse_csv
from fiat.driver.handler import BufferHandler, FileBufferHandler


## Paths to data and temporary data
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
@pytest.fixture(scope="session")
def table_array() -> np.ndarray:
    data = np.array([[1, 3], [2, 4]])
    return data


@pytest.fixture
def vulnerability_table(vulnerability_path: Path):
    bh = FileBufferHandler(vulnerability_path)
    return parse_csv(bh, delimiter=",", header=True)


## Mixed dtype csv buffers for the compiled parser
@pytest.fixture
def mixed_buffer() -> BytesIO:
    b = BytesIO()
    b.write(
        b"""# metadata is skipped
id,count,ratio,label
row-a,1,1.5,alpha
row-b,2,,beta
row-c,3,3.25,gamma
"""
    )
    b.seek(0)
    return b


@pytest.fixture
def mixed_buffer_handler(mixed_buffer: BytesIO) -> BufferHandler:
    h = BufferHandler(mixed_buffer)
    h.nchar = b"\n"
    h.size = h.stream.read().count(h.nchar)
    return h


@pytest.fixture
def numeric_buffer() -> BytesIO:
    b = BytesIO()
    b.write(b"1,2.5\n3,4.0\n")
    b.seek(0)
    return b


@pytest.fixture
def numeric_buffer_handler(numeric_buffer: BytesIO) -> BufferHandler:
    h = BufferHandler(numeric_buffer)
    h.nchar = b"\n"
    h.size = h.stream.read().count(h.nchar)
    return h


## FlatGeobuf geometries (one per geometry type)
@pytest.fixture(scope="session")
def fgb_point() -> fgb.Geometry:
    # POINT (1 2)
    return fgb.make_geometry(fgb.GT_POINT, [1.0, 2.0])


@pytest.fixture(scope="session")
def fgb_multipoint() -> fgb.Geometry:
    # MULTIPOINT (0 0, 2 3)
    return fgb.make_geometry(fgb.GT_MULTIPOINT, [0.0, 0.0, 2.0, 3.0])


@pytest.fixture(scope="session")
def fgb_linestring() -> fgb.Geometry:
    # LINESTRING (0 0, 2 1, 4 1)
    return fgb.make_geometry(fgb.GT_LINESTRING, [0.0, 0.0, 2.0, 1.0, 4.0, 1.0])


@pytest.fixture(scope="session")
def fgb_multilinestring() -> fgb.Geometry:
    # MULTILINESTRING ((0 0, 1 0), (3 2, 4 2))
    xy = [0.0, 0.0, 1.0, 0.0, 3.0, 2.0, 4.0, 2.0]
    return fgb.make_geometry(fgb.GT_MULTILINESTRING, xy, ends=[2, 4])


@pytest.fixture(scope="session")
def fgb_polygon_hole() -> fgb.Geometry:
    # POLYGON ((0 0, 4 0, 4 4, 0 4, 0 0), (1 1, 3 1, 3 3, 1 3, 1 1))
    xy = [
        0.0, 0.0, 4.0, 0.0, 4.0, 4.0, 0.0, 4.0, 0.0, 0.0,
        1.0, 1.0, 3.0, 1.0, 3.0, 3.0, 1.0, 3.0, 1.0, 1.0,
    ]  # fmt: skip
    return fgb.make_geometry(fgb.GT_POLYGON, xy, ends=[5, 10])


@pytest.fixture(scope="session")
def fgb_multipolygon() -> fgb.Geometry:
    # MULTIPOLYGON (((0 0, 1 0, 1 1, 0 1, 0 0)), ((2 2, 3 2, 3 3, 2 3, 2 2)))
    xy = [
        0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0, 0.0, 0.0,
        2.0, 2.0, 3.0, 2.0, 3.0, 3.0, 2.0, 3.0, 2.0, 2.0,
    ]  # fmt: skip
    return fgb.make_geometry(fgb.GT_MULTIPOLYGON, xy, ends=[5, 10], parts=[1, 2])
