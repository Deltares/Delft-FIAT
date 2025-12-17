from pathlib import Path

import pytest

from fiat.cfg import Configurations


@pytest.fixture
def config_empty(tmp_path: Path) -> Configurations:
    c = Configurations(_root=tmp_path)
    assert c.path == tmp_path
    return c


@pytest.fixture
def config_exposure_geom(
    config: Configurations,
) -> Configurations:
    config.set(
        "exposure.geom",
        [
            {"file": "exposure/spatial.geojson"},
            {"file": "exposure/spatial2.geojson"},
        ],
    )
    return config
