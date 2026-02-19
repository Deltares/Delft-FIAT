from pathlib import Path

import numpy as np

from fiat.fio import GridIO
from fiat.method import flood
from fiat.model.util import (
    create_1d_chunks,
    create_2d_chunks,
    create_2d_windows,
    get_band_names,
    get_hazard_meta,
    get_vulnerability_meta,
    vectorize_function,
)
from fiat.struct import Table


def test_create_1d_chunks_few():
    # Call the function
    chunks = list(create_1d_chunks(500, 6))

    # Assert the output
    assert len(chunks) == 6
    assert chunks[0] == (1, 84)
    assert chunks[-1] == (421, 500)


def test_create_1d_chunks_many():
    # Call the function
    chunks = list(create_1d_chunks(500, 20))

    # Assert the output
    assert len(chunks) == 20
    assert chunks[0] == (1, 25)
    assert chunks[-1] == (476, 500)


def test_create_2d_chunks_few():
    # Call the function
    chunks = list(create_2d_chunks((500, 350), 2))

    # Assert the output
    assert len(chunks) == 4
    assert chunks[0] == (0, 0, 354, 248)
    assert chunks[2] == (354, 0, 146, 248)


def test_create_2d_chunks_many():
    # Call the function
    chunks = list(create_2d_chunks((500, 350), 10))

    # Assert the output
    assert len(chunks) == 16
    assert chunks[4] == (158, 0, 158, 111)
    assert chunks[10] == (316, 222, 158, 111)


def test_create_2d_windows_even():
    # Call the function
    windows = list(create_2d_windows((10, 10), (0, 0), (2, 2)))

    # Assert the output
    assert len(windows) == 25
    assert windows[0] == (0, 0, 2, 2)
    assert windows[-1] == (8, 8, 2, 2)  # Should nicely fit


def test_create_2d_windows_uneven():
    # Call the function
    windows = list(create_2d_windows((10, 10), (0, 0), (4, 4)))
    assert len(windows) == 9
    assert windows[0] == (0, 0, 4, 4)
    assert windows[-1] == (8, 8, 2, 2)  # It's the same as it does not fit


def test_get_band_names(hazard_event_path: Path):
    # Setup the object
    gio = GridIO(hazard_event_path)

    # Call the function
    names = get_band_names(gio)

    # Assert the output
    assert names == ["band1"]


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
    meta = get_hazard_meta(hazard_event_data, risk=False, method=flood)

    # Assert the output
    assert meta.density is None
    assert meta.ids == ["1"]
    assert meta.indices_run == [[0]]
    assert meta.indices_type == [[0]]
    assert meta.risk == False
    assert meta.rp is None
    assert meta.type == "flood"


def test_get_hazard_meta_risk(hazard_risk_data: GridIO):
    # Call the function
    meta = get_hazard_meta(hazard_risk_data, risk=True, method=flood)

    # Assert the output
    np.testing.assert_array_almost_equal(
        meta.density,
        [0.17, 0.18, 0.08, 0.07],
        decimal=2,
    )
    assert meta.ids == ["2", "5", "10", "25"]
    assert meta.indices_run == [[0], [1], [2], [3]]
    assert meta.indices_type == [[0, 1, 2, 3]]
    assert meta.risk == True
    assert meta.rp == [2, 5, 10, 25]
    assert meta.type == "flood"


def test_get_vulnerability_meta(vulnerability_data_run: Table):
    # Call the function
    meta = get_vulnerability_meta(vulnerability_data_run)

    # Assert the output
    assert meta.min == 0
    assert meta.max == 5


# Create a dummy function
def foo(x, c_a, c_b):
    return x * c_a + c_b


def test_vectorize_function():
    # Call the function
    foo_vec = vectorize_function(fn=foo, skip=1)

    # Call the vectorized function
    out = foo_vec(np.array([1, 2]), 10, 12)

    # Assert the output
    np.testing.assert_array_equal(out, [22, 32])
