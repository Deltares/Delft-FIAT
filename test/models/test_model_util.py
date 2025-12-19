from pathlib import Path

import numpy as np

from fiat.fio import GridIO
from fiat.models.util import get_band_names, get_hazard_meta, get_vulnerability_meta
from fiat.struct import Table


def test_get_band_names(hazard_event_path: Path):
    # Setup the object
    gio = GridIO(hazard_event_path)

    # Call the function
    names = get_band_names(gio)

    # Assert the output
    assert names == ["Band1"]


def test_get_band_names_empty(tmp_path: Path):
    # Setup the object
    gio = GridIO(Path(tmp_path, "tmp.tif"), mode="w")
    gio.create((2, 2), 1, 6)

    # Call the function
    names = get_band_names(gio)

    # Assert the output
    assert names == ["band1"]  # Notice that the first letter is not capitalized


def test_get_hazard_meta(hazard_event_data: GridIO):
    # Call the function
    meta = get_hazard_meta(hazard_event_data, risk=False)

    # Assert the output
    assert meta.density is None
    assert meta.names == ["Band1"]
    assert meta.risk == False
    assert meta.rp is None
    assert meta.type == "flood"


def test_get_hazard_meta_risk(hazard_risk_data: GridIO):
    # Call the function
    meta = get_hazard_meta(hazard_risk_data, risk=True)

    # Assert the output
    np.testing.assert_array_almost_equal(
        meta.density,
        [0.17, 0.18, 0.08, 0.07],
        decimal=2,
    )
    assert meta.names == ["Band1", "Band2", "Band3", "Band4"]
    assert meta.risk == True
    assert meta.rp == [2, 5, 10, 25]
    assert meta.type == "flood"


def test_get_vulnerability_meta(vulnerability_data_run: Table):
    # Call the function
    meta = get_vulnerability_meta(vulnerability_data_run)

    # Assert the output
    assert meta.min == 0
    assert meta.max == 5
    assert meta.sigdec == 3
