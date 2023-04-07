from delft_fiat.cfg import ConfigReader
from delft_fiat.io import open_geom, open_grid

import pytest
from pathlib import Path


@pytest.fixture
def cfg():
    c = ConfigReader(Path(Path.cwd(), ".testdata", "settings.toml"))
    return c


@pytest.fixture
def gm(cfg):
    d = open_geom(cfg.get_path("exposure.geom_file"))
    return d


@pytest.fixture
def gr(cfg):
    d = open_grid(cfg.get_path("hazard.grid_file"))
    return d
