import shutil
from pathlib import Path

import pytest

from fiat.fio import GeomIO, open_geom
from fiat.fio.handler import BufferHandler


@pytest.fixture(scope="session")
def exposure_geom_dataset(exposure_geom_path: Path):
    ds = open_geom(exposure_geom_path)  # Read only
    assert isinstance(ds, GeomIO)
    return ds


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


@pytest.fixture
def exposure_geom_tmp_path(tmp_path: Path, exposure_geom_path: Path) -> Path:
    p = Path(tmp_path, "tmp.geojson")
    shutil.copy2(exposure_geom_path, p)
    assert p.is_file()
    return p


@pytest.fixture(scope="session")
def handler(exposure_data_path: Path) -> BufferHandler:
    h = BufferHandler(exposure_data_path)
    return h


@pytest.fixture(scope="session")
def handler_meta(testdata_dir: Path) -> BufferHandler:
    h = BufferHandler(Path(testdata_dir, "exposure", "spatial_meta.csv"))
    return h
