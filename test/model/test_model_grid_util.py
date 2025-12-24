from fiat.fio import GridIO
from fiat.model.grid_util import get_exposure_meta
from fiat.struct.container import HazardMeta, VulnerabilityMeta


def test_get_exposure_meta(
    exposure_grid_data: GridIO,
    hazard_meta_run: HazardMeta,
    vulnerability_meta_run: VulnerabilityMeta,
):
    # Call the function
    meta = get_exposure_meta(
        exposure=exposure_grid_data,
        hazard_meta=hazard_meta_run,
        vulnerability_meta=vulnerability_meta_run,
    )

    # Assert the output
    assert meta.fn_list == ["struct_1", "struct_2"]
    assert meta.nb == 3
    assert meta.new == ["band1_1", "band2_1", "total_1"]
