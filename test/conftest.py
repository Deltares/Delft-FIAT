import io
import platform
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock

import pytest
from osgeo import osr
from pytest_mock import MockerFixture

from fiat.cfg import Configurations
from fiat.fio import GeomIO, GridIO, open_csv, open_geom, open_grid
from fiat.log import Logger
from fiat.struct import Table

TEST_MODULE = Path(__file__).parent


## Globally defined fixtures (for easy access)
@pytest.fixture(scope="session")
def os_type() -> int:
    s = platform.system()
    if s.lower() == "linux":
        return 0
    elif s.lower() == "windows":
        return 1
    else:
        raise OSError("Non")


@pytest.fixture(scope="session")
def testdata_dir() -> Path:
    p = Path(TEST_MODULE, "..", ".testdata").resolve()
    assert Path(p, "geom_event.toml").is_file()
    return p


## Path to key files
@pytest.fixture(scope="session")
def exposure_geom_path(testdata_dir: Path) -> Path:
    p = Path(testdata_dir, "exposure", "spatial.geojson")
    assert p.is_file()
    return p


@pytest.fixture(scope="session")
def exposure_data_path(testdata_dir: Path) -> Path:
    p = Path(testdata_dir, "exposure", "spatial.csv")
    assert p.is_file()
    return p


@pytest.fixture(scope="session")
def hazard_event_path(testdata_dir: Path) -> Path:
    p = Path(testdata_dir, "hazard", "event_map.nc")
    assert p.is_file()
    return p


@pytest.fixture(scope="session")
def hazard_risk_path(testdata_dir: Path) -> Path:
    p = Path(testdata_dir, "hazard", "risk_map.nc")
    assert p.is_file()
    return p


@pytest.fixture(scope="session")
def vulnerability_path(testdata_dir: Path) -> Path:
    p = Path(testdata_dir, "vulnerability", "vulnerability_curves.csv")
    assert p.is_file()
    return p


## Globally used object
@pytest.fixture
def config(testdata_dir: Path) -> Configurations:
    c = Configurations(
        _root=testdata_dir,
        _name="tmp.toml",
    )
    return c


@pytest.fixture
def exposure_cols() -> dict:
    c = {
        "object_id": 0,
        "fn_damage_structure": 1,
        "fn_damage_content": 2,
        "max_damage_structure": 3,
        "max_damage_content": 4,
    }
    return c


@pytest.fixture
def exposure_data_fn() -> dict:
    data = {
        "fn": {
            "_structure": 1,
        },
        "max": {
            "_structure": 3,
        },
    }
    return data


@pytest.fixture(scope="session")
def exposure_geom_dataset(exposure_geom_path: Path) -> GeomIO:
    ds = open_geom(exposure_geom_path)  # Read only
    assert isinstance(ds, GeomIO)
    return ds


@pytest.fixture(scope="session")
def hazard_event_data(hazard_event_path: Path) -> GridIO:
    ds = open_grid(hazard_event_path)  # Read only
    assert isinstance(ds, GridIO)
    return ds


@pytest.fixture(scope="session")
def hazard_risk_sub_data(hazard_risk_path: Path) -> GridIO:
    ds = open_grid(hazard_risk_path, var_as_band=False)  # Read only
    assert isinstance(ds, GridIO)
    return ds


@pytest.fixture
def log_capture() -> io.StringIO:
    buffer = io.StringIO()
    return buffer


@pytest.fixture
def logger_stream(log_capture: io.StringIO) -> Logger:
    logger = Logger("fiat")
    logger.add_stream_handler(name="Capture", level=2, stream=log_capture)
    return logger


@pytest.fixture
def mocked_exp_grid(mocker: MockerFixture, srs: osr.SpatialReference) -> MagicMock:
    grid = mocker.create_autospec(GridIO)
    # Set attributes for practical use
    type(grid).geotransform = PropertyMock(
        side_effect=lambda: (0, 1.0, 0.0, 10.0, 0.0, -1.0),
    )
    type(grid).srs = PropertyMock(side_effect=lambda: srs)
    type(grid).shape = PropertyMock(side_effect=lambda: (10, 10))
    return grid


@pytest.fixture
def mocked_hazard_grid(mocker: MockerFixture, srs: osr.SpatialReference) -> MagicMock:
    grid = mocker.create_autospec(GridIO)
    # Set attributes for practical use
    type(grid).geotransform = PropertyMock(
        side_effect=lambda: (0, 1.0, 0.0, 10.0, 0.0, -1.0),
    )
    type(grid).srs = PropertyMock(side_effect=lambda: srs)
    type(grid).shape = PropertyMock(side_effect=lambda: (10, 10))
    return grid


@pytest.fixture(scope="session")
def srs() -> osr.SpatialReference:
    s = osr.SpatialReference()
    s.SetFromUserInput("EPSG:4326")
    return s


@pytest.fixture(scope="session")
def vulnerability_data(vulnerability_path: Path) -> Table:
    ds = open_csv(vulnerability_path, index="water depth")
    assert isinstance(ds, Table)
    return ds
