import numpy as np

from fiat.method.ead import fn_density, fn_ead


def test_fn_density():
    # Call the function
    coef = fn_density(rp=[1, 2, 5, 25, 50, 100])

    # Assert the output
    np.testing.assert_array_almost_equal(
        coef,
        [0.28, 0.39, 0.23, 0.07, 0.01, 0.01],
        decimal=2,
    )


def test_fn_density_order():
    # Call the function
    coef = fn_density(rp=[50, 2, 100, 25, 1, 5])

    # Assert the output
    np.testing.assert_array_almost_equal(
        coef,
        [0.01, 0.39, 0.01, 0.07, 0.28, 0.23],  # Same numbers different order
        decimal=2,
    )


def test_fn_density_single():
    # Call the function
    coef = fn_density([2])

    # Assert the output
    np.testing.assert_almost_equal(coef, 0.5)


def test_fn_ead():
    # Call the function
    ead = fn_ead(
        rp_coef=[0.28, 0.39, 0.23, 0.07, 0.01, 0.01],
        impact=[5, 10, 50, 300, 1200, 3000],
    )

    # Assert the output
    np.testing.assert_almost_equal(ead, 79.8)


def test_fn_ead_order():
    # Call the function
    ead = fn_ead(
        rp_coef=[0.01, 0.39, 0.01, 0.07, 0.28, 0.23],
        impact=[1200, 10, 3000, 300, 5, 50],
    )

    # Assert the output
    np.testing.assert_almost_equal(ead, 79.8)  # Same


def test_fn_ead_single():
    # Call the function
    ead = fn_ead([0.1], [5])  # i.e. 1/10 Y

    # Assert the output
    np.testing.assert_almost_equal(ead, 0.5)
