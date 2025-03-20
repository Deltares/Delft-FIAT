import shutil
from pathlib import Path

import pytest

from fiat.cfg import Configurations
from fiat.cli.main import args_parser
from fiat.fio import open_csv, open_geom, open_grid
from fiat.log import LogItem
from fiat.models import GeomModel, GridModel

_GEOM_FILES = [
    "hazard.file",
    "exposure.geom.file1",
    "exposure.csv.file",
    "vulnerability.file",
]
_MODELS = [
    "geom_event",
    "geom_event_2g",
    "geom_event_missing",
    "geom_event_outside",
    "geom_risk",
    "geom_risk_2g",
    "grid_event",
    "grid_risk",
    "grid_unequal",
    "missing_hazard",
    "missing_models",
]
_PATH = Path.cwd()


@pytest.fixture
def cli_parser():
    return args_parser()


@pytest.fixture
def settings_files():
    _files = {}
    for _m in _MODELS:
        p = Path(_PATH, ".testdata", f"{_m}.toml")
        p_name = p.stem
        _files[p_name] = p
    return _files


@pytest.fixture
def configs(settings_files):
    _cfgs = {}
    for key, item in settings_files.items():
        if not key.startswith("missing"):
            _cfgs[key] = Configurations.from_file(item)
    return _cfgs


## Models
@pytest.fixture
def geom_tmp_model(tmp_path, configs):
    cfg = configs["geom_event"]
    settings_file = Path(tmp_path, "settings.toml")
    shutil.copy2(cfg.filepath, settings_file)
    for file in _GEOM_FILES:
        path = cfg.get(file)
        new_path = Path(tmp_path, path.parent.name)
        new_path.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, Path(new_path, path.name))
    assert settings_file.is_file()
    return settings_file


@pytest.fixture
def geom_risk(configs):
    model = GeomModel(configs["geom_risk"])
    return model


@pytest.fixture
def grid_risk(configs):
    model = GridModel(configs["grid_risk"])
    return model


## Data
@pytest.fixture(scope="session")
def geom_data():
    d = open_geom(Path(_PATH, ".testdata", "exposure", "spatial.geojson"))
    return d


## Data
@pytest.fixture(scope="session")
def geom_outside_data():
    d = open_geom(Path(_PATH, ".testdata", "exposure", "spatial_outside.geojson"))
    return d


@pytest.fixture(scope="session")
def geom_partial_data():
    d = open_csv(Path(_PATH, ".testdata", "exposure", "spatial_partial.csv"), lazy=True)
    return d


@pytest.fixture
def grid_event_data():
    d = open_grid(Path(_PATH, ".testdata", "hazard", "event_map.nc"))
    return d


@pytest.fixture(scope="session")
def grid_event_highres_data():
    d = open_grid(Path(_PATH, ".testdata", "hazard", "event_map_highres.nc"))
    return d


@pytest.fixture(scope="session")
def grid_exp_data():
    d = open_grid(Path(_PATH, ".testdata", "exposure", "spatial.nc"))
    return d


@pytest.fixture(scope="session")
def grid_risk_data():
    d = open_grid(Path(_PATH, ".testdata", "hazard", "risk_map.nc"))
    return d


@pytest.fixture(scope="session")
def vul_path():
    path = Path(_PATH, ".testdata", "vulnerability", "vulnerability_curves.csv")
    assert path.exists()
    return path


@pytest.fixture(scope="session")
def vul_raw_data(vul_path):
    with open(vul_path, mode="rb") as f:
        data = f.read()
    return data


@pytest.fixture(scope="session")
def vul_data(vul_path):
    d = open_csv(vul_path)
    return d


@pytest.fixture(scope="session")
def vul_data_win():
    d = open_csv(
        Path(_PATH, ".testdata", "vulnerability", "vulnerability_curves_win.csv"),
    )
    return d


@pytest.fixture
def log1():
    obj = LogItem(level=2, msg="Hello!")
    return obj


@pytest.fixture
def log2():
    obj = LogItem(level=2, msg="Good Bye!")
    return obj
