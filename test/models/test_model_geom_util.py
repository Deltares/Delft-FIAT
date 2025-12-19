from fiat.methods import flood
from fiat.models.geom_util import get_exposure_meta


def test_get_exposure_meta():
    # Call the function
    meta = get_exposure_meta(
        columns={
            "oid": 0,
            "ref": 1,
            "fn_damage_structure": 2,
            "max_damage_structure": 3,
        },
        module=flood,
        types=["damage"],
        bands=["band1"],
        risk=False,
    )

    # Assert the output
    assert meta.indices_new == [4, 5, 6]
    assert meta.type_length == 3
    assert meta.new == ["depth_band1", "damage_structure_band1", "total_damage_band1"]
    assert meta.indices_total == [-1]
    assert list(meta.indices_type) == ["damage"]


def test_get_exposure_meta_risk():
    meta = get_exposure_meta(
        columns={"oid": 0, "ref": 1, "fn_damage": 2, "max_damage": 3},
        module=flood,
        types=["damage"],
        bands=["band1"],
        risk=True,
    )

    # Assert the output
    assert meta.indices_new == [4, 5, 6, 7]
    assert meta.type_length == 3
    assert "ead_damage" in meta.new


def test_get_exposure_meta_multi():
    # Call the function
    meta = get_exposure_meta(
        columns={
            "oid": 0,
            "ref": 1,
            "fn_damage": 2,
            "max_damage": 3,
            "fn_affected": 4,
            "max_affected": 5,
        },
        module=flood,
        types=["damage", "affected"],
        bands=["band1"],
        risk=False,
    )

    # Assert the output
    assert meta.indices_new == [6, 7, 8, 9, 10]
    assert meta.type_length == 5
    assert "damage_band1" in meta.new
    assert "affected_band1" in meta.new
    assert meta.indices_total == [-3, -1]
    assert list(meta.indices_type) == ["damage", "affected"]
