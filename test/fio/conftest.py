import shutil
from pathlib import Path

import pytest

from fiat.fio import GeomIO, open_geom


@pytest.fixture(scope="session")
def exposure_geom_dataset(exposure_geom_path: Path):
    ds = open_geom(exposure_geom_path)  # Read only
    assert isinstance(ds, GeomIO)
    return ds


@pytest.fixture
def exposure_geom_tmp_path(tmp_path: Path, exposure_geom_path: Path) -> Path:
    p = Path(tmp_path, "spatial.geojson")
    shutil.copy2(exposure_geom_path, p)
    assert p.is_file()
    return p
