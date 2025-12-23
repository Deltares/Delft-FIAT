from fiat.fio import GeomIO
from fiat.method import flood
from fiat.model.geom_util import get_exposure_meta
from fiat.struct.container import HazardMeta


def test_get_exposure_meta(
    exposure_geom_data: GeomIO,
    hazard_meta_run: HazardMeta,
):
    # Call the function
    meta = get_exposure_meta(
        exposure=exposure_geom_data,
        hazard_meta=hazard_meta_run,
        module=flood,
        types=["damage"],
    )

    # Assert the output
    assert meta.indices_new == [5, 6, 7]
    assert meta.type_length == 3
    assert meta.new == ["depth_band1", "damage_structure_band1", "total_damage_band1"]
    assert meta.indices_total == [-1]
    assert list(meta.indices_type) == ["damage"]


def test_get_exposure_meta_risk(
    exposure_geom_data: GeomIO,
    hazard_risk_meta_run: HazardMeta,
):
    meta = get_exposure_meta(
        exposure=exposure_geom_data,
        hazard_meta=hazard_risk_meta_run,
        module=flood,
        types=["damage"],
    )

    # Assert the output
    assert meta.indices_new == list(range(5, 18))
    assert meta.type_length == 3
    assert "ead_damage" in meta.new


# def test_get_exposure_meta_multi(
#     hazard_meta_run: HazardMeta,
# ):
#     # Call the function
#     meta = get_exposure_meta(
#         columns={
#             "oid": 0,
#             "ref": 1,
#             "fn_damage": 2,
#             "max_damage": 3,
#             "fn_affected": 4,
#             "max_affected": 5,
#         },
#         hazard_meta=hazard_meta_run,
#         module=flood,
#         types=["damage", "affected"],
#     )
#
#     # Assert the output
#     assert meta.indices_new == [6, 7, 8, 9, 10]
#     assert meta.type_length == 5
#     assert "damage_band1" in meta.new
#     assert "affected_band1" in meta.new
#     assert meta.indices_total == [-3, -1]
#     assert list(meta.indices_type) == ["damage", "affected"]
