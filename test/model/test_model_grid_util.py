from fiat.container import HazardMeta, RunMeta, VulnerabilityMeta
from fiat.driver import NetcdfReader
from fiat.model.grid_util import equal_grid, get_exposure_meta
from fiat.util import EXPOSURE


def test_get_exposure_meta(
    exposure_grid_data: NetcdfReader,
    run_meta: RunMeta,
    hazard_meta_run: HazardMeta,
    vulnerability_meta_run: VulnerabilityMeta,
):
    # Call the function
    meta = get_exposure_meta(
        exposure=exposure_grid_data,
        run_meta=run_meta,
        hazard_meta=hazard_meta_run,
        vulnerability_meta=vulnerability_meta_run,
    )

    # Assert the output
    assert meta.fn_list == ["struct_1", "struct_2"]
    assert meta.index_ead is None
    assert meta.indices_new == [[0, 1]]
    assert meta.indices_total == [2]
    assert meta.nb == 3
    assert meta.new == ["exposure1_1", "exposure2_1", "total_1"]


def test_get_exposure_meta_risk(
    exposure_grid_data: NetcdfReader,
    run_risk_meta: RunMeta,
    hazard_risk_meta_run: HazardMeta,
    vulnerability_meta_run: VulnerabilityMeta,
):
    # Call the function
    meta = get_exposure_meta(
        exposure=exposure_grid_data,
        run_meta=run_risk_meta,
        hazard_meta=hazard_risk_meta_run,
        vulnerability_meta=vulnerability_meta_run,
    )

    # Assert the output
    assert meta.fn_list == ["struct_1", "struct_2"]
    assert meta.index_ead == 12
    assert meta.indices_new == [[0, 4], [1, 5], [2, 6], [3, 7]]
    assert meta.indices_total == [8, 9, 10, 11]
    assert meta.nb == 13
    assert "exposure1_5" in meta.new
    assert "exposure2_10" in meta.new
    assert "total_25" in meta.new
    assert "ead" in meta.new


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
