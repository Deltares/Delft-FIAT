import io
import platform
from multiprocessing import get_context
from multiprocessing.queues import Queue
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
    p = Path(TEST_MODULE, "..", "data").resolve()
    assert Path(p, "geom_event.toml").is_file()
    return p


## Path to key files
@pytest.fixture(scope="session")
def exposure_geom_path(testdata_dir: Path) -> Path:
    p = Path(testdata_dir, "exposure", "spatial.geojson")
    assert p.is_file()
    return p


@pytest.fixture(scope="session")
def exposure_grid_path(testdata_dir: Path) -> Path:
    p = Path(testdata_dir, "exposure", "spatial.nc")
    assert p.is_file()
    return p


@pytest.fixture(scope="session")
def hazard_event_path(testdata_dir: Path) -> Path:
    p = Path(testdata_dir, "event_map.nc")
    assert p.is_file()
    return p


@pytest.fixture(scope="session")
def hazard_event_highres_path(testdata_dir: Path) -> Path:
    p = Path(testdata_dir, "event_map_highres.nc")
    assert p.is_file()
    return p


@pytest.fixture(scope="session")
def hazard_risk_path(testdata_dir: Path) -> Path:
    p = Path(testdata_dir, "risk_map.nc")
    assert p.is_file()
    return p


@pytest.fixture(scope="session")
def vulnerability_path(testdata_dir: Path) -> Path:
    p = Path(testdata_dir, "vulnerability", "curves.csv")
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


@pytest.fixture(scope="session")
def exposure_geom_data(exposure_geom_path: Path) -> GeomIO:
    ds = open_geom(exposure_geom_path)  # Read only
    assert isinstance(ds, GeomIO)
    return ds


@pytest.fixture
def exposure_grid_data(exposure_grid_path: Path) -> GridIO:
    ds = open_grid(exposure_grid_path, var_as_band=True)  # Read only
    assert isinstance(ds, GridIO)
    return ds


@pytest.fixture(scope="session")
def hazard_event_data(hazard_event_path: Path) -> GridIO:
    ds = open_grid(hazard_event_path)  # Read only
    assert isinstance(ds, GridIO)
    return ds


@pytest.fixture
def hazard_event_highres_data(hazard_event_highres_path: Path) -> GridIO:
    ds = open_grid(hazard_event_highres_path)  # Read only
    assert isinstance(ds, GridIO)
    return ds


@pytest.fixture(scope="session")
def hazard_risk_data(hazard_risk_path: Path) -> GridIO:
    ds = open_grid(hazard_risk_path, var_as_band=True)  # Read only
    assert isinstance(ds, GridIO)
    return ds


@pytest.fixture(scope="session")
def hazard_risk_data_subsets(hazard_risk_path: Path) -> GridIO:
    ds = open_grid(hazard_risk_path, var_as_band=False)  # Read only
    assert isinstance(ds, GridIO)
    return ds


@pytest.fixture
def mocked_exp_grid(
    mocker: MockerFixture,
    srs_4326: osr.SpatialReference,
) -> MagicMock:
    grid = mocker.create_autospec(GridIO)
    # Set attributes for practical use
    type(grid).geotransform = PropertyMock(
        side_effect=lambda: (0, 1.0, 0.0, 10.0, 0.0, -1.0),
    )
    type(grid).srs = PropertyMock(side_effect=lambda: srs_4326)
    type(grid).shape = PropertyMock(side_effect=lambda: (10, 10))
    return grid


@pytest.fixture
def mocked_hazard_grid(
    mocker: MockerFixture,
    srs_4326: osr.SpatialReference,
) -> MagicMock:
    grid = mocker.create_autospec(GridIO)
    # Set attributes for practical use
    type(grid).geotransform = PropertyMock(
        side_effect=lambda: (0, 1.0, 0.0, 10.0, 0.0, -1.0),
    )
    type(grid).srs = PropertyMock(side_effect=lambda: srs_4326)
    type(grid).shape = PropertyMock(side_effect=lambda: (10, 10))
    return grid


@pytest.fixture
def mp_queue() -> Queue:
    ctx = get_context()
    q = Queue(ctx=ctx, maxsize=2)
    return q


@pytest.fixture(scope="session")
def srs_4326() -> osr.SpatialReference:
    s = osr.SpatialReference()
    s.SetFromUserInput("EPSG:4326")
    return s


@pytest.fixture(scope="session")
def srs_3857() -> osr.SpatialReference:
    s = osr.SpatialReference()
    s.SetFromUserInput("EPSG:3857")
    return s


@pytest.fixture(scope="session")
def vulnerability_data(vulnerability_path: Path) -> Table:
    ds = open_csv(vulnerability_path, index="depth")
    assert isinstance(ds, Table)
    return ds


## Capturing logging messages
class CapLogger(Logger):
    """Logging class for capturing texting logging."""

    @property
    def text(self) -> str:
        stream = self._handlers[0].stream
        stream.seek(0)
        return stream.read()


@pytest.fixture
def log_buffer() -> io.StringIO:
    buffer = io.StringIO()
    return buffer


@pytest.fixture
def caplog(log_buffer: io.StringIO) -> CapLogger:
    logger = CapLogger("fiat")
    logger._handlers = []
    logger.add_stream_handler(name="Capture", level=2, stream=log_buffer)
    return logger
