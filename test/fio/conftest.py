import shutil
from pathlib import Path

import pytest

from fiat.fio import open_geom
from fiat.fio.handler import BufferHandler


## Paths to data and temporary data
@pytest.fixture
def exposure_geom_empty_tmp_path(tmp_path: Path, exposure_geom_dataset: Path) -> Path:
    p = Path(tmp_path, "tmp.geojson")
    with open_geom(p, mode="w") as writer:
        writer.create_layer(
            exposure_geom_dataset.layer.srs,
            exposure_geom_dataset.layer.geom_type,
        )
        writer.layer.set_from_defn(exposure_geom_dataset.layer.defn)
    assert p.is_file()
    return p


@pytest.fixture(scope="session")
def exposure_geom_no_srs_path(testdata_dir: Path):
    p = Path(testdata_dir, "exposure", "spatial_no_srs.fgb")
    assert p.is_file()
    return p


@pytest.fixture
def exposure_geom_tmp_path(tmp_path: Path, exposure_geom_path: Path) -> Path:
    p = Path(tmp_path, "tmp.geojson")
    shutil.copy2(exposure_geom_path, p)
    assert p.is_file()
    return p


@pytest.fixture(scope="session")
def hazard_event_no_srs_path(testdata_dir: Path):
    p = Path(testdata_dir, "event_map_no_srs.nc")
    assert p.is_file()
    return p


@pytest.fixture
def hazard_event_tmp_path(tmp_path: Path, hazard_event_path: Path) -> Path:
    p = Path(tmp_path, "tmp.nc")
    shutil.copy2(hazard_event_path, p)
    assert p.is_file()
    return p


## Objects/ data structures
@pytest.fixture(scope="session")
def handler(vulnerability_path: Path) -> BufferHandler:
    h = BufferHandler(vulnerability_path)
    return h


## Objects/ data structures
@pytest.fixture
def handler_dummy(vulnerability_path: Path) -> BufferHandler:
    h = BufferHandler(vulnerability_path)

    return h


@pytest.fixture(scope="session")
def vulnerability_win_path(testdata_dir: Path) -> Path:
    p = Path(testdata_dir, "vulnerability", "curves_win.csv")
    assert p.is_file()
    return p
