from pathlib import Path

import pytest
from fiat.cfg import ConfigReader
from fiat.io import open_geom, open_grid
from fiat.log import LogItem


@pytest.fixture()
def settings_toml_event():
    return Path(Path.cwd(), ".testdata", "settings.toml")


@pytest.fixture()
def settings_toml_grid():
    return Path(Path.cwd(), ".testdata", "settings_grid.toml")


@pytest.fixture()
def settings_toml_risk():
    return Path(Path.cwd(), ".testdata", "settings_risk.toml")


@pytest.fixture()
def cfg_geom_event(settings_toml_event):
    c = ConfigReader(settings_toml_event)
    return c


@pytest.fixture()
def cfg_geom_event_mis():
    p = Path(Path.cwd(), ".testdata", "settings_missing.toml")
    return ConfigReader(p)


@pytest.fixture()
def cfg_geom_risk(settings_toml_risk):
    c = ConfigReader(settings_toml_risk)
    return c


@pytest.fixture()
def cfg_grid_event(settings_toml_grid):
    c = ConfigReader(settings_toml_grid)
    return c


@pytest.fixture()
def cfg_grid_risk(settings_toml_grid):
    p = Path(Path.cwd(), ".testdata", "settings_grid_risk.toml")
    return ConfigReader(p)


@pytest.fixture()
def gm(cfg_geom_event):
    d = open_geom(cfg_geom_event.get_path("exposure.geom.file1"))
    return d


@pytest.fixture()
def gr_event(cfg_geom_event):
    d = open_grid(cfg_geom_event.get_path("hazard.file"))
    return d


@pytest.fixture()
def gr_risk(cfg_geom_risk):
    d = open_grid(cfg_geom_risk.get_path("hazard.file"), var_as_band=True)
    return d


@pytest.fixture()
def log1():
    obj = LogItem(level=2, msg="Hello!")
    return obj


@pytest.fixture()
def log2():
    obj = LogItem(level=2, msg="Good Bye!")
    return obj
