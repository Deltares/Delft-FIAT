import io
import platform
import shutil
from multiprocessing import get_context
from multiprocessing.queues import Queue
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pyproj.crs import CRS

from fiat.cfg import Configurations
from fiat.driver import FlatGeobufReader, NetcdfReader, Table
from fiat.log import Logger
from fiat.open import open_csv, open_geom, open_grid

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
    p = Path(testdata_dir, "exposure", "spatial.fgb")
    assert p.is_file()
    return p


@pytest.fixture
def exposure_geom_tmp_path(tmp_path: Path, exposure_geom_path: Path) -> Path:
    p = Path(tmp_path, "tmp.fgb")
    shutil.copy2(exposure_geom_path, p)
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


@pytest.fixture
def hazard_event_tmp_path(tmp_path: Path, hazard_event_path: Path) -> Path:
    p = Path(tmp_path, "event_map.nc")
    shutil.copy2(hazard_event_path, p)
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
def exposure_geom_data(exposure_geom_path: Path) -> FlatGeobufReader:
    ds = open_geom(exposure_geom_path)  # Read only
    assert isinstance(ds, FlatGeobufReader)
    return ds


@pytest.fixture
def exposure_grid_data(exposure_grid_path: Path) -> NetcdfReader:
    ds = open_grid(exposure_grid_path)  # Read only
    ds.load()
    assert isinstance(ds, NetcdfReader)
    return ds


@pytest.fixture(scope="session")
def hazard_event_data(hazard_event_path: Path) -> NetcdfReader:
    ds = open_grid(hazard_event_path)  # Read only
    ds.load()
    assert isinstance(ds, NetcdfReader)
    return ds


@pytest.fixture
def hazard_event_highres_data(hazard_event_highres_path: Path) -> NetcdfReader:
    ds = open_grid(hazard_event_highres_path)  # Read only
    assert isinstance(ds, NetcdfReader)
    return ds


@pytest.fixture(scope="session")
def hazard_risk_data(hazard_risk_path: Path) -> NetcdfReader:
    ds = open_grid(hazard_risk_path)  # Read only
    ds.load()
    assert isinstance(ds, NetcdfReader)
    return ds


@pytest.fixture(scope="session")
def hazard_risk_data_subsets(hazard_risk_path: Path) -> NetcdfReader:
    ds = open_grid(hazard_risk_path)  # Read only
    assert isinstance(ds, NetcdfReader)
    return ds


@pytest.fixture
def mocked_exp_grid(
    crs_4326: CRS,
) -> MagicMock:
    grid = MagicMock()
    # Set attributes for practical use on the shared profile
    grid.profile = MagicMock()
    grid.profile.transform = (0, 1.0, 0.0, 10.0, 0.0, -1.0)
    grid.profile.crs = crs_4326
    grid.profile.shape = (10, 10)
    return grid


@pytest.fixture
def mocked_hazard_grid(
    crs_4326: CRS,
) -> MagicMock:
    grid = MagicMock()
    # Set attributes for practical use on the shared profile
    grid.profile = MagicMock()
    grid.profile.transform = (0, 1.0, 0.0, 10.0, 0.0, -1.0)
    grid.profile.crs = crs_4326
    grid.profile.shape = (10, 10)
    return grid


@pytest.fixture
def mp_queue() -> Queue:
    ctx = get_context()
    q = Queue(ctx=ctx, maxsize=2)
    return q


@pytest.fixture(scope="session")
def crs_4326() -> CRS:
    s = CRS.from_user_input("EPSG:4326")
    return s


@pytest.fixture(scope="session")
def crs_3857() -> CRS:
    s = CRS.from_user_input("EPSG:3857")
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
