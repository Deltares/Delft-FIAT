import platform
from pathlib import Path

import pytest

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
