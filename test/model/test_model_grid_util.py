from fiat.driver import NetcdfReader
from fiat.model.grid_util import equal_grid
from fiat.util import EXPOSURE


def test_equal_grid(
    hazard_event_data: NetcdfReader,
    exposure_grid_data: NetcdfReader,
):
    # Assert the current state
    assert hazard_event_data.profile.shape == (10, 10)
    assert exposure_grid_data.profile.shape == (10, 10)

    # Call the function
    ds1, ds2 = equal_grid(
        gs1=hazard_event_data,
        gs2=exposure_grid_data,
    )

    # Assert same
    assert ds1.profile.shape == (10, 10)
    assert ds2.profile.shape == (10, 10)


def test_equal_grid_unequal(
    hazard_event_highres_data: NetcdfReader,
    hazard_event_data: NetcdfReader,
):
    # Assert the current state
    assert hazard_event_highres_data.profile.shape == (100, 100)
    assert hazard_event_data.profile.shape == (10, 10)

    # Call the function
    ds1, ds2 = equal_grid(
        gs1=hazard_event_highres_data,
        gs2=hazard_event_data,
    )

    # Assert exposure data is resampled to 100, 100
    assert ds1.profile.shape == (100, 100)
    assert ds2.profile.shape == (100, 100)


def test_equal_grid_unequal_second(
    hazard_event_highres_data: NetcdfReader,
    exposure_grid_data: NetcdfReader,
):
    # Assert the current state
    assert hazard_event_highres_data.profile.shape == (100, 100)
    assert exposure_grid_data.profile.shape == (10, 10)

    # Call the function
    ds1, ds2 = equal_grid(
        gs1=hazard_event_highres_data,
        gs2=exposure_grid_data,
        base=EXPOSURE,
    )

    # Assert hazard data is resampled to 10, 10
    assert ds1.profile.shape == (10, 10)
    assert ds2.profile.shape == (10, 10)
