import numpy as np

from fiat.driver import NetcdfReader, Table
from fiat.method import flood
from fiat.model.meta import (
    ExposureGeomData,
    HazardMeta,
    RunMeta,
    VulnerabilityMeta,
    get_exposure_geom_meta,
    get_exposure_grid_meta,
    get_hazard_meta,
    get_run_meta,
    get_vulnerability_meta,
)


def test_get_run_meta():
    # Call the function
    meta = get_run_meta(
        risk=False,
        method=flood.depth,
    )

    # Assert the output
    assert not meta.risk
    assert meta.type == "flood.depth"
    assert meta.type_length == 1


def test_get_vulnerability_meta(vulnerability_data_run: Table):
    # Call the function
    meta = get_vulnerability_meta(vulnerability_data_run)

    # Assert the output
    assert meta.min == 0
    assert meta.max == 5


def test_get_hazard_meta(hazard_event_data: NetcdfReader):
    # Call the function
    meta = get_hazard_meta(hazard_event_data, risk=False, method_types=["water_depth"])

    # Assert the output
    assert meta.density is None
    assert meta.ids == ["1"]
    assert meta.indices_run == [[0]]
    assert meta.indices_type == [[0]]
    assert meta.rp is None


def test_get_hazard_meta_risk(hazard_risk_data: NetcdfReader):
    # Call the function
    meta = get_hazard_meta(hazard_risk_data, risk=True, method_types=["water_depth"])

    # Assert the output
    np.testing.assert_array_almost_equal(
        meta.density,
        [0.17, 0.18, 0.08, 0.07],
        decimal=2,
    )
    assert meta.ids == ["2", "5", "10", "25"]
    assert meta.indices_run == [[0], [1], [2], [3]]
    assert meta.indices_type == [[0, 1, 2, 3]]
    assert meta.rp == [2, 5, 10, 25]


def test_get_exposure_geom_meta(
    exposure_geom_data_run: ExposureGeomData,
    run_meta: RunMeta,
    hazard_meta_run: HazardMeta,
):
    # Call the function
    meta = get_exposure_geom_meta(
        exposure=exposure_geom_data_run,
        run_meta=run_meta,
        hazard_meta=hazard_meta_run,
        method=flood.depth,
    )

    # Assert the output
    assert meta.area_method == "area"
    assert meta.indices_impact == {"damage": [(1,)]}
    assert meta.indices_new == [5, 6, 7]
    assert meta.indices_spec == [2]
    assert meta.indices_total == {"damage": [2]}
    assert meta.indices_type == {"damage": [[3, 4]]}
    assert meta.new == ["depth_1", "damage_structure_1", "total_damage_1"]
    assert meta.new_length == 3
    assert meta.type_length == 3
    assert meta.zonal_method == "mean"


def test_get_exposure_geom_meta_risk(
    exposure_geom_data_run: ExposureGeomData,
    run_risk_meta: RunMeta,
    hazard_risk_meta_run: HazardMeta,
):
    meta = get_exposure_geom_meta(
        exposure=exposure_geom_data_run,
        run_meta=run_risk_meta,
        hazard_meta=hazard_risk_meta_run,
        method=flood.depth,
    )

    # Assert the output
    assert meta.indices_impact == {"damage": [(1,), (4,), (7,), (10,)]}
    assert meta.indices_new == list(range(5, 18, 1))
    assert meta.indices_spec == [2]
    assert meta.indices_total == {"damage": [2, 5, 8, 11]}
    assert meta.indices_type == {"damage": [[3, 4]]}
    assert "depth_2" in meta.new
    assert "total_damage_5" in meta.new
    assert "ead_damage" in meta.new
    assert meta.new_length == 13
    assert meta.type_length == 3


def test_get_exposure_grid_meta(
    exposure_grid_data: NetcdfReader,
    run_meta: RunMeta,
    hazard_meta_run: HazardMeta,
    vulnerability_meta_run: VulnerabilityMeta,
):
    # Call the function
    meta = get_exposure_grid_meta(
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


def test_get_exposure_grid_meta_risk(
    exposure_grid_data: NetcdfReader,
    run_risk_meta: RunMeta,
    hazard_risk_meta_run: HazardMeta,
    vulnerability_meta_run: VulnerabilityMeta,
):
    # Call the function
    meta = get_exposure_grid_meta(
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
