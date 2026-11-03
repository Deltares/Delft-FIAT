import numpy as np

from fiat._core import InterpND
from fiat.method.flood import depth_duration, depth_duration_2d
from fiat.method.flood.depth_duration_2d import fn_impact
from fiat.util import FLOOD_DEPTH_DURATION_2D


def test_attributes():
    # Assert the method definitions
    assert depth_duration_2d.NAME == FLOOD_DEPTH_DURATION_2D
    assert depth_duration_2d.NDATASETS == 1
    assert depth_duration_2d.TYPES == ["water_depth", "duration"]
    assert depth_duration_2d.AXIS_TYPES == ["water_depth", "duration"]
    assert depth_duration_2d.COLUMNS is depth_duration.COLUMNS
    assert depth_duration_2d.NEW_COLUMNS is depth_duration.NEW_COLUMNS
    assert depth_duration_2d.fn_hazard is depth_duration.fn_hazard


def test_depth_duration_2d_impact():
    # Call the function
    fn = InterpND(([0, 5], [0, 10]), [[0, 0], [0.5, 1]])
    out = fn_impact((5.0, 5.0), 1000, (fn,), 1.0)

    # Assert the output
    assert out == 750.0


def test_depth_duration_2d_impact_array():
    # Call the function with arrays (grid)
    fn = InterpND(([0, 5], [0, 10]), [[0, 0], [0.5, 1]])
    out = fn_impact(
        (np.array([5.0, np.nan]), np.array([5.0, 5.0])),
        np.array([1000.0, 1000.0]),
        (fn,),
        0.5,
    )

    # Assert the output
    np.testing.assert_array_almost_equal(out, [375.0, np.nan])
