import numpy as np

from fiat.methods.flood import (
    calculate_hazard,
)
from fiat.struct import Table


def test_calculate_hazard():
    # Call the function
    dmg, red_f = calculate_hazard(
        [2.5, 5, 10],
        reference="dem",
        ground_flht=1.0,
        ground_elevtn=0,
        method="mean",
    )

    # Assert the output
    np.testing.assert_almost_equal(dmg, 4.83, decimal=2)
    np.testing.assert_almost_equal(red_f, 1.0)

    # Call the function with a zero value added
    dmg, red_f = calculate_hazard(
        [0, 2.5, 5, 10],
        reference="dem",
        ground_flht=1.0,
        ground_elevtn=0,
        method="mean",
    )

    # Assert the output
    np.testing.assert_almost_equal(dmg, 4.83, decimal=2)
    np.testing.assert_almost_equal(red_f, 0.75)


def test_calculate_hazard_datum():
    # Call the function with reference to datum
    dmg, red_f = calculate_hazard(
        [0, 2.5, 5, 10],
        reference="datum",
        ground_flht=1.0,
        ground_elevtn=1.0,
        method="mean",
    )

    # Assert the output
    assert int(dmg * 100) == 383
    assert int(red_f * 100) == 75

    # Call the function with different input
    dmg, red_f = calculate_hazard(
        [0, 1.5, 5, 10],
        reference="datum",
        ground_flht=1.0,
        ground_elevtn=1.0,
        method="mean",
    )

    # Assert the output
    assert int(dmg * 100) == 350
    assert int(red_f * 100) == 75


def test_calculate_damage(
    exposure_data_fn: dict,
    vulnerability_data: Table,
):
    vulnerability_data.upscale(0.01, inplace=True)
    pass
