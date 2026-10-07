import pickle

import numpy as np
import pytest

from fiat._core import Interp1D


def test_interp1d():
    # Set the object
    fn = Interp1D([0.0, 2.0, 5.0], [0.0, 4.0, 10.0])

    # Assert exact values at and between the knots
    np.testing.assert_almost_equal(fn(0.0), 0.0)  # On a knot
    np.testing.assert_almost_equal(fn(2.0), 4.0)  # On a knot
    np.testing.assert_almost_equal(fn(1.0), 2.0)  # Between knots
    np.testing.assert_almost_equal(fn(3.5), 7.0)  # Between knots


def test_interp1d_extrapolate():
    # Set the object
    fn = Interp1D([1.0, 3.0, 6.0], [2.0, 6.0, 12.0])

    # Assert linear extrapolation along the first and last segment
    np.testing.assert_almost_equal(fn(0.0), 0.0)  # Below the first knot
    np.testing.assert_almost_equal(fn(9.0), 18.0)  # Above the last knot


def test_interp1d_nan():
    # Set the object
    fn = Interp1D([0.0, 1.0], [0.0, 2.0])

    # A nan query propagates to a nan result
    assert np.isnan(fn(np.nan))


def test_interp1d_array():
    # Set the object
    fn = Interp1D([0.0, 2.0], [0.0, 4.0])

    # Call with an array-like, the shape is preserved
    out = fn([[0.0, 0.5], [1.0, 2.0]])

    # Assert the output
    assert isinstance(out, np.ndarray)
    assert out.dtype == np.float64
    assert out.shape == (2, 2)
    np.testing.assert_array_almost_equal(out, [[0.0, 1.0], [2.0, 4.0]])


def test_interp1d_scalar():
    # Set the object
    fn = Interp1D([0.0, 2.0], [0.0, 4.0])

    # A scalar query returns a plain float
    out = fn(1.0)

    # Assert the output
    assert isinstance(out, float)
    np.testing.assert_almost_equal(out, 2.0)


def test_interp1d_mismatch():
    # x and y of different length are rejected
    with pytest.raises(ValueError, match="same length"):
        Interp1D([0.0, 1.0], [0.0])


def test_interp1d_empty():
    # An empty grid has too few points
    with pytest.raises(ValueError, match="at least two"):
        Interp1D([], [])


def test_interp1d_single():
    # A single point is still too few to interpolate
    with pytest.raises(ValueError, match="at least two"):
        Interp1D([0.0], [1.0])


def test_interp1d_pickle():
    # Set the object
    fn = Interp1D([0.0, 1.0, 3.0], [0.0, 2.0, 8.0])

    # Round trip through pickle (needed for multiprocessing)
    restored = pickle.loads(pickle.dumps(fn))

    # Assert the restored object behaves the same
    assert isinstance(restored, Interp1D)
    np.testing.assert_array_almost_equal(restored([0.5, 2.0, 4.0]), [1.0, 5.0, 11.0])
