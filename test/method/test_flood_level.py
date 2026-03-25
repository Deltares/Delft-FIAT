import numpy as np

from fiat.method.flood.level import fn_hazard


def test_fn_hazard():
    # Call the function
    dmg, red_f = fn_hazard(
        [2.5, 5, 10],
        reference=0.0,
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
        reference=0.0,
        elevation=1.0,
        method="mean",
    )

    # Assert the output
    assert np.isnan(dmg)


def test_fn_hazard_red():
    # Call the function with a zero value added
    dmg, red_f = fn_hazard(
        [0, 2.5, 5, 10],
        reference=2.0,
        elevation=1.0,
        method="mean",
    )

    # Assert the output
    np.testing.assert_almost_equal(dmg, 4.83, decimal=2)
    np.testing.assert_almost_equal(red_f, 0.75)


def test_fn_hazard_high_elev():
    # Call the function with higher ref
    dmg, red_f = fn_hazard(
        [0, 2.5, 5, 10],
        reference=0.0,
        elevation=2.0,
        method="mean",
    )

    # Assert the output
    np.testing.assert_almost_equal(dmg, 3.83, decimal=2)
    np.testing.assert_almost_equal(red_f, 0.75)


def test_fn_hazard_high_ref():
    # Call the function with higher ref
    dmg, red_f = fn_hazard(
        [0, 2.5, 5, 10],
        reference=4.0,
        elevation=2.0,
        method="mean",
    )

    # Assert the output
    np.testing.assert_almost_equal(dmg, 5.5, decimal=2)
    np.testing.assert_almost_equal(red_f, 0.5)


def test_fn_hazard_high_elev_red():
    # Call the function with different input
    dmg, red_f = fn_hazard(
        [0, 0, 5, 10],
        reference=1.0,
        elevation=2.0,
        method="mean",
    )

    # Assert the output
    np.testing.assert_almost_equal(dmg, 5.5, decimal=2)
    np.testing.assert_almost_equal(red_f, 0.5)
