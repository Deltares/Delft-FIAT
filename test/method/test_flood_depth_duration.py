import math

import numpy as np

from fiat._core import Interp1D
from fiat.method.flood import depth_duration
from fiat.method.flood.depth_duration import fn_hazard, fn_impact
from fiat.util import DEPTH, DURATION, FLOOD_DEPTH_DURATION


def test_attributes():
    # Assert the method definitions
    assert depth_duration.NAME == FLOOD_DEPTH_DURATION
    assert depth_duration.NDATASETS == 2
    assert depth_duration.TYPES == ["water_depth", "duration"]
    assert depth_duration.AXIS_TYPES == ["water_depth", "duration"]
    assert depth_duration.COLUMNS == ["elevation"]
    assert depth_duration.NEW_COLUMNS == [DEPTH, DURATION]


def test_depth_duration_hazard():
    # Call the function
    out = fn_hazard(
        (np.array([1.0, 1.0]), np.array([4.0, 4.0])),
        0.5,
        method="mean",
    )

    # Assert the output
    assert out == ((0.5, 4.0), 1.0)


def test_depth_duration_hazard_fact():
    # The reduction factor comes from the depth
    (d, t), fact = fn_hazard(
        (np.array([0.0, 2.0]), np.array([2.0, 6.0])),
        1.0,
        method="max",
    )

    # Assert the output
    assert d == 1.0
    assert t == 6.0
    assert fact == 0.5


def test_depth_duration_hazard_zero_duration():
    # Wet object with zero duration gives a finite duration and impact
    (d, t), fact = fn_hazard(
        (np.array([1.0, 1.0]), np.array([0.0, 0.0])),
        0.5,
        method="mean",
    )

    # Assert the output
    assert (d, t, fact) == (0.5, 0.0, 1.0)
    curves = (Interp1D([0, 5], [0, 1]), Interp1D([0, 10], [0.5, 1]))
    assert fn_impact((d, t), 1000, curves, fact) == 50.0


def test_depth_duration_hazard_dry_pixels():
    # Duration is reduced over the wet pixels only
    (d, t), fact = fn_hazard(
        (np.array([0.0, 2.0, 4.0, np.nan]), np.array([8.0, 2.0, 4.0, 6.0])),
        1.0,
        method="mean",
    )

    # Assert the output
    assert d == 2.0
    assert t == 3.0
    assert fact == 0.5


def test_depth_duration_hazard_duration_nan():
    # Nodata duration on a wet pixel gives no duration
    (d, t), _ = fn_hazard(
        (np.array([1.0, 1.0]), np.array([np.nan, 4.0])),
        0.5,
        method="max",
    )

    # Assert the output
    assert d == 0.5
    assert math.isnan(t)


def test_depth_duration_hazard_none():
    # No depth means no hazard
    (d, t), fact = fn_hazard(
        (np.array([0.0, 0.0]), np.array([4.0, 4.0])),
        0.5,
        method="mean",
    )

    # Assert the output
    assert math.isnan(d)
    assert math.isnan(t)
    assert math.isnan(fact)


def test_depth_duration_impact():
    # Call the function
    curves = (Interp1D([0, 5], [0, 1]), Interp1D([0, 10], [0, 1]))
    out = fn_impact((2.5, 5.0), 1000, curves, 1.0)

    # Assert the output
    assert out == 250.0


def test_depth_duration_impact_array():
    # Call the function with arrays (grid)
    curves = (Interp1D([0, 5], [0, 1]), Interp1D([0, 10], [0, 1]))
    out = fn_impact(
        (np.array([2.5, np.nan, 5.0]), np.array([5.0, 5.0, np.nan])),
        np.array([1000.0, 1000.0, 1000.0]),
        curves,
        0.5,
    )

    # Assert the output
    np.testing.assert_array_almost_equal(out, [125.0, np.nan, np.nan])
