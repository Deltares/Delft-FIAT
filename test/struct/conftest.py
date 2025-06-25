from pathlib import Path

import pytest

from fiat.fio import GeomIO, open_geom


## I/O structures needed for this testing
@pytest.fixture
def exposure_geom_write(tmp_path) -> GeomIO:
    ds = open_geom(Path(tmp_path, "tmp.geojson"), mode="w")  # Read only
    assert isinstance(ds, GeomIO)
    return ds
