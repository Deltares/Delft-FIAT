import shutil
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from fiat.driver.csv import CSVParser

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
def vulnerability_parsed(vulnerability_path: Path) -> CSVParser:
    bh = FileBufferHandler(vulnerability_path)
    p = CSVParser(bh, delimiter=",", header=True)
    return p
