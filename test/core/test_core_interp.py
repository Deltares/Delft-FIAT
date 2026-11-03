import math
import pickle

import numpy as np
import pytest

from fiat._core import Interp1D, InterpND


def test_interp1d():
    # Set the object
    fn = Interp1D([0.0, 2.0, 5.0], [0.0, 4.0, 10.0])

    # Assert exact values at and between the knots
    np.testing.assert_almost_equal(fn(0.0), 0.0)  # On a knot
    np.testing.assert_almost_equal(fn(2.0), 4.0)  # On a knot
    np.testing.assert_almost_equal(fn(1.0), 2.0)  # Between knots
    np.testing.assert_almost_equal(fn(3.5), 7.0)  # Between knots


def test_interp1d_outside_grid():
    # Set the object
    fn = Interp1D([1.0, 3.0, 6.0], [2.0, 6.0, 12.0])

    # Queries outside the grid hold the boundary values (no extrapolation)
    np.testing.assert_almost_equal(fn(0.0), 2.0)  # Below the first knot
    np.testing.assert_almost_equal(fn(-5.0), 2.0)  # Far below the first knot
    np.testing.assert_almost_equal(fn(9.0), 12.0)  # Above the last knot
    np.testing.assert_array_almost_equal(fn([0.0, 9.0]), [2.0, 12.0])  # Array call


def test_interp1d_negative_depth():
    # A damage curve starting at (0, 0), queried below the ground floor (issue #205)
    fn = Interp1D([0.0, 0.2, 1.0], [0.0, 0.1965981, 1.0])

    # Water below the first curve depth causes no damage, not negative damage
    np.testing.assert_almost_equal(fn(-0.164498), 0.0)
    assert fn(-0.164498) * 6766.98 == 0.0


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
    # (4.0 lies above the last knot and holds the last value)
    np.testing.assert_array_almost_equal(restored([0.5, 2.0, 4.0]), [1.0, 5.0, 8.0])


@pytest.fixture
def interpnd() -> InterpND:
    return InterpND(([0, 1, 2], [0, 10]), [[0, 0], [1, 2], [2, 4]])


def test_interpnd(interpnd: InterpND):
    # Assert values between and on the knots
    np.testing.assert_almost_equal(interpnd(1.0, 5.0), 1.5)
    np.testing.assert_almost_equal(interpnd(0.5, 0.0), 0.5)
    np.testing.assert_almost_equal(interpnd(2.0, 10.0), 4.0)
    assert isinstance(interpnd(1.0, 5.0), float)


def test_interpnd_3d():
    # Linear function f(x, y, z) = x + 2y + 3z is reproduced exactly
    axes = ([0.0, 1.0, 3.0], [0.0, 2.0], [0.0, 1.0, 2.0, 4.0])
    grid = np.meshgrid(*axes, indexing="ij")
    values = grid[0] + 2 * grid[1] + 3 * grid[2]
    fn = InterpND(axes, values)
    np.testing.assert_almost_equal(fn(2.0, 0.5, 3.0), 2.0 + 1.0 + 9.0)


def test_interpnd_outside_grid(interpnd: InterpND):
    # Queries outside the grid are clamped per axis
    np.testing.assert_almost_equal(interpnd(-1, -5), 0.0)
    np.testing.assert_almost_equal(interpnd(9, 99), 4.0)
    np.testing.assert_almost_equal(interpnd(1.0, 99), 2.0)


def test_interpnd_array(interpnd: InterpND):
    # Call with arrays, the shape is preserved
    out = interpnd(np.array([1.0, 2.0]), np.array([5.0, 10.0]))
    assert isinstance(out, np.ndarray)
    assert out.dtype == np.float64
    np.testing.assert_array_almost_equal(out, [1.5, 4.0])

    out = interpnd(np.ones((2, 2)), np.full((2, 2), 5.0))
    assert out.shape == (2, 2)
    np.testing.assert_array_almost_equal(out, np.full((2, 2), 1.5))


def test_interpnd_nan(interpnd: InterpND):
    # Any nan input gives a nan output
    assert math.isnan(interpnd(math.nan, 1.0))
    assert math.isnan(interpnd(1.0, math.nan))
    out = interpnd(np.array([1.0, math.nan]), np.array([math.nan, 5.0]))
    assert np.isnan(out).all()


def test_interpnd_pickle(interpnd: InterpND):
    # Pickle round trip
    fn = pickle.loads(pickle.dumps(interpnd))
    np.testing.assert_almost_equal(fn(1.0, 5.0), 1.5)


def test_interpnd_shape_error():
    # Only one axis
    with pytest.raises(ValueError, match="at least two axes"):
        InterpND(([0, 1],), [[0, 1]])
    # Number of axes not equal to the number of value dimensions
    with pytest.raises(ValueError, match="number of axes"):
        InterpND(([0, 1], [0, 1]), [0, 1])
    # Axis length not equal to the value dimension length
    with pytest.raises(ValueError, match="length of axis 0"):
        InterpND(([0, 1, 2], [0, 1]), [[0, 1], [1, 2]])


def test_interpnd_query_error(interpnd: InterpND):
    # Wrong number of query arguments
    with pytest.raises(ValueError, match="expected 2 query arguments"):
        interpnd(1.0)
