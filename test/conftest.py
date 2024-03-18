from pathlib import Path

import pytest
from fiat.cfg import ConfigReader
from fiat.cli.main import args_parser
from fiat.io import open_csv, open_geom, open_grid
from fiat.log import LogItem
from fiat.models import GeomModel, GridModel

_MODELS = [
    "geom_event",
    "geom_event_2g",
    "geom_event_missing",
    "geom_risk",
    "geom_risk_2g",
    "grid_event",
    "grid_risk",
]


@pytest.fixture()
def cli_parser():
    return args_parser()


@pytest.fixture()
def settings_files():
    _files = {}
    for _m in _MODELS:
        p = Path(Path.cwd(), ".testdata", f"{_m}.toml")
        p_name = p.stem
        _files[p_name] = p
    return _files


@pytest.fixture()
def configs(settings_files):
    _cfgs = {}
    for key, item in settings_files.items():
        _cfgs[key] = ConfigReader(item)
    return _cfgs


@pytest.fixture()
def geom_risk(configs):
    model = GeomModel(configs["geom_risk"])
    return model


@pytest.fixture()
def grid_risk(configs):
    model = GridModel(configs["grid_risk"])
    return model


@pytest.fixture()
def geom_data():
    d = open_geom(Path(Path.cwd(), ".testdata", "exposure", "spatial.gpkg"))
    return d


@pytest.fixture()
def grid_event_data():
    d = open_grid(Path(Path.cwd(), ".testdata", "hazard", "event_map.nc"))
    return d


@pytest.fixture()
def grid_risk_data():
    d = open_grid(Path(Path.cwd(), ".testdata", "hazard", "risk_map.nc"))
    return d


@pytest.fixture()
def vul_data():
    d = open_csv(
        Path(Path.cwd(), ".testdata", "vulnerability", "vulnerability_curves.csv")
    )
    return d


@pytest.fixture()
def log1():
    obj = LogItem(level=2, msg="Hello!")
    return obj


@pytest.fixture()
def log2():
    obj = LogItem(level=2, msg="Good Bye!")
    return obj
