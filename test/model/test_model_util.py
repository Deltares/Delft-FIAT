import numpy as np

from fiat.driver import NetcdfReader, Table
from fiat.method import flood
from fiat.model.util import (
    create_1d_chunks,
    create_2d_chunks,
    create_2d_windows,
    get_hazard_meta,
    get_run_meta,
    get_vulnerability_meta,
)


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
    assert len(chunks) == 2
    assert chunks[0] == (0, 0, 250, 350)
    assert chunks[1] == (250, 0, 250, 350)


def test_create_2d_chunks_many():
    # Call the function
    chunks = list(create_2d_chunks((500, 350), 10))

    # Assert the output
    assert len(chunks) == 10
    assert chunks[4] == (167, 105, 167, 105)
    assert chunks[7] == (125, 210, 125, 140)


def test_create_2d_windows_even():
    # Call the function
    windows = list(create_2d_windows((10, 10), (0, 0), (2, 2)))

    # Assert the output
    assert len(windows) == 25
    assert windows[0] == (slice(0, 2), slice(0, 2))
    assert windows[-1] == (slice(8, 10), slice(8, 10))  # Should nicely fit


def test_create_2d_windows_uneven():
    # Call the function
    windows = list(create_2d_windows((10, 10), (0, 0), (4, 4)))
    assert len(windows) == 9
    assert windows[0] == (slice(0, 4), slice(0, 4))
    assert windows[-1] == (slice(8, 10), slice(8, 10))
    # It's the same as it does not fit


def test_get_run_meta():
    # Call the function
    meta = get_run_meta(
        risk=False,
        method=flood.depth,
    )

    # Assert the output
    assert not meta.risk
    assert meta.type == "flood.depth"
    assert meta.type_length == 1


def test_get_hazard_meta(hazard_event_data: NetcdfReader):
    # Call the function
    meta = get_hazard_meta(hazard_event_data, risk=False, method_types=["water_depth"])

    # Assert the output
    assert meta.density is None
    assert meta.ids == ["1"]
    assert meta.indices_run == [[0]]
    assert meta.indices_type == [[0]]
    assert meta.rp is None


def test_get_hazard_meta_risk(hazard_risk_data: NetcdfReader):
    # Call the function
    meta = get_hazard_meta(hazard_risk_data, risk=True, method_types=["water_depth"])

    # Assert the output
    np.testing.assert_array_almost_equal(
        meta.density,
        [0.17, 0.18, 0.08, 0.07],
        decimal=2,
    )
    assert meta.ids == ["2", "5", "10", "25"]
    assert meta.indices_run == [[0], [1], [2], [3]]
    assert meta.indices_type == [[0, 1, 2, 3]]
    assert meta.rp == [2, 5, 10, 25]


def test_get_vulnerability_meta(vulnerability_data_run: Table):
    # Call the function
    meta = get_vulnerability_meta(vulnerability_data_run)

    # Assert the output
    assert meta.min == 0
    assert meta.max == 5
