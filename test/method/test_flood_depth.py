from typing import Callable

import numpy as np

from fiat.method.flood.depth import (
    fn_hazard,
    fn_impact,
)


def test_fn_hazard():
    # Call the function
    dmg, red_f = fn_hazard(
        [2.5, 5, 10],
        elevation=1.0,
        method="mean",
    )

    # Assert the output
    np.testing.assert_almost_equal(dmg, 4.83, decimal=2)
    np.testing.assert_almost_equal(red_f, 1.0)


def test_fn_hazard_none():
    # Call the function
    dmg, _ = fn_hazard(
        [],
        elevation=1.0,
        method="mean",
    )

    # Assert the output
    assert np.isnan(dmg)


def test_fn_hazard_red():
    # Call the function with a zero value added
    dmg, red_f = fn_hazard(
        [0, 2.5, 5, 10],
        elevation=1.0,
        method="mean",
    )

    # Assert the output
    np.testing.assert_almost_equal(dmg, 4.83, decimal=2)
    np.testing.assert_almost_equal(red_f, 0.75)


def test_fn_hazard_high_ref():
    # Call the function with higher ref
    dmg, red_f = fn_hazard(
        [0, 2.5, 5, 10],
        elevation=2.0,
        method="mean",
    )

    # Assert the output
    np.testing.assert_almost_equal(dmg, 3.83, decimal=2)
    np.testing.assert_almost_equal(red_f, 0.75)


def test_fn_hazard_high_ref_red():
    # Call the function with different input
    dmg, red_f = fn_hazard(
        [0, 0, 5, 10],
        elevation=2.0,
        method="mean",
    )

    # Assert the output
    np.testing.assert_almost_equal(dmg, 5.5, decimal=2)
    np.testing.assert_almost_equal(red_f, 0.5)


def test_fn_impact(
    vulnerability_fn1: Callable,
):
    # Call the function
    out = fn_impact(
        hazard=5.5,
        exposure=4000,
        fact=1,
        fn_curve=vulnerability_fn1,
    )

    # Assert the output
    np.testing.assert_almost_equal(out, 2803.8, decimal=1)


def test_fn_impact_fact(
    vulnerability_fn1: Callable,
):
    # Call the function
    out = fn_impact(
        hazard=5.5,
        exposure=4000,
        fact=0.5,
        fn_curve=vulnerability_fn1,
    )

    # Assert the output
    np.testing.assert_almost_equal(out, 1401.9, decimal=1)
