import numpy as np

from fiat._core import Interp1D
from fiat.method.flood import depth
from fiat.method.flood.depth import (
    fn_hazard,
    fn_impact,
)


def test_attributes():
    # Assert the method definitions
    assert depth.NDATASETS == 1
    assert depth.TYPES == ["water_depth"]
    assert depth.AXIS_TYPES == ["water_depth"]
    assert not hasattr(depth, "INDEX")


def test_fn_hazard():
    # Call the function
    (dmg,), red_f = fn_hazard(
        (np.array([2.5, 5, 10], dtype=float),),
        1.0,
        method="mean",
    )

    # Assert the output
    np.testing.assert_almost_equal(dmg, 4.83, decimal=2)
    np.testing.assert_almost_equal(red_f, 1.0)


def test_fn_hazard_none():
    # Call the function
    (dmg,), red_f = fn_hazard(
        (np.array([], dtype=float),),
        1.0,
        method="mean",
    )

    # Assert the output
    assert np.isnan(dmg)
    assert np.isnan(red_f)


def test_fn_hazard_red():
    # Call the function with a zero value added
    (dmg,), red_f = fn_hazard(
        (np.array([0, 2.5, 5, 10], dtype=float),),
        1.0,
        method="mean",
    )

    # Assert the output
    np.testing.assert_almost_equal(dmg, 4.83, decimal=2)
    np.testing.assert_almost_equal(red_f, 0.75)


def test_fn_hazard_high_ref():
    # Call the function with higher ref
    (dmg,), red_f = fn_hazard(
        (np.array([0, 2.5, 5, 10], dtype=float),),
        2.0,
        method="mean",
    )

    # Assert the output
    np.testing.assert_almost_equal(dmg, 3.83, decimal=2)
    np.testing.assert_almost_equal(red_f, 0.75)


def test_fn_hazard_high_ref_red():
    # Call the function with different input
    (dmg,), red_f = fn_hazard(
        (np.array([0, 0, 5, 10], dtype=float),),
        2.0,
        method="mean",
    )

    # Assert the output
    np.testing.assert_almost_equal(dmg, 5.5, decimal=2)
    np.testing.assert_almost_equal(red_f, 0.5)


def test_fn_impact():
    # Call the function
    out = fn_impact((2.0,), 1000, (Interp1D([0, 5], [0, 1]),), 1.0)

    # Assert the output
    assert out == 400.0


def test_fn_impact_curve(
    vulnerability_fn1: Interp1D,
):
    # Call the function, beyond the curve the last value is held
    out = fn_impact((5.5,), 4000, (vulnerability_fn1,), 1)

    # Assert the output
    np.testing.assert_almost_equal(out, 3840.0, decimal=1)


def test_fn_impact_fact(
    vulnerability_fn1: Interp1D,
):
    # Call the function
    out = fn_impact((2.75,), 4000, (vulnerability_fn1,), 0.5)

    # Assert the output
    np.testing.assert_almost_equal(out, 1260.0, decimal=1)


def test_fn_impact_array():
    # Call the function with arrays (grid)
    out = fn_impact(
        (np.array([2.0, np.nan, 5.0]),),
        np.array([1000.0, 1000.0, 500.0]),
        (Interp1D([0, 5], [0, 1]),),
        1.0,
    )

    # Assert the output
    np.testing.assert_array_almost_equal(out, [400.0, np.nan, 500.0])
