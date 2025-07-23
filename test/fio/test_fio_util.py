from pathlib import Path

from fiat.fio import GridIO
from fiat.fio.util import deter_band_names


def test_deter_band_names(hazard_event_path: Path):
    # Setup the object
    gio = GridIO(hazard_event_path)

    # Call the function
    names = deter_band_names(gio)

    # Assert the output
    assert names == ["Band1"]


def test_deter_band_names_empty(tmp_path: Path):
    # Setup the object
    gio = GridIO(Path(tmp_path, "tmp.tif"), mode="w")
    gio.create((2, 2), 1, 6)

    # Call the function
    names = deter_band_names(gio)

    # Assert the output
    assert names == ["band1"]  # Notice that the first letter is not capitalized
