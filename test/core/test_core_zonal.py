import numpy as np

from fiat._core import zonal_reduce


def test_zonal_reduce_mean():
    # Mix of nan, non-positive and positive values
    arr = np.ascontiguousarray([np.nan, -1.0, 0.0, 2.0, 4.0], dtype=np.float64)

    # Call the function with the mean code (0)
    value, red_f = zonal_reduce(arr, 0, 0.0)

    # Assert the output
    np.testing.assert_almost_equal(value, 3.0)
    np.testing.assert_almost_equal(red_f, 0.4)  # 2 of 5 cells positive


def test_zonal_reduce_max():
    arr = np.ascontiguousarray([np.nan, -1.0, 0.0, 2.0, 4.0], dtype=np.float64)

    # Call the function with the max code (1)
    value, red_f = zonal_reduce(arr, 1, 0.0)

    # Assert the output
    np.testing.assert_almost_equal(value, 4.0)
    np.testing.assert_almost_equal(red_f, 0.4)


def test_zonal_reduce_min():
    arr = np.ascontiguousarray([np.nan, -1.0, 0.0, 2.0, 4.0], dtype=np.float64)

    # Call the function with the min code (2)
    value, red_f = zonal_reduce(arr, 2, 0.0)

    # Assert the output
    np.testing.assert_almost_equal(value, 2.0)
    np.testing.assert_almost_equal(red_f, 0.4)


def test_zonal_reduce_sub():
    arr = np.ascontiguousarray([1.0, 3.0, 6.0], dtype=np.float64)

    # Subtract a reference before filtering and reducing
    value, red_f = zonal_reduce(arr, 0, 2.0)

    # Assert the output, 1.0 drops out as non-positive
    np.testing.assert_almost_equal(value, 2.5)
    np.testing.assert_almost_equal(red_f, 2.0 / 3.0)


def test_zonal_reduce_none():
    # No positive cells left after the filter
    arr = np.ascontiguousarray([np.nan, -1.0, 0.0], dtype=np.float64)

    # Call the function
    value, red_f = zonal_reduce(arr, 0, 0.0)

    # Assert the output
    assert np.isnan(value)
    assert np.isnan(red_f)
