from fiat.model.geom_util import (
    discover_exp_columns,
    generate_output_columns,
)


def test_discover_columns_found(exposure_cols: dict):
    # Call the function
    dmg_suffix, dmg_idx, missing = discover_exp_columns(exposure_cols, type="damage")
    assert dmg_suffix == ["_structure", "_content"]
    assert dmg_idx[0] == [1, 3]  # First is function, second is max
    assert dmg_idx[1] == [2, 4]
    assert len(missing) == 0


def test_discover_columns_missing(exposure_cols: dict):
    # Pop an entry for max damage
    _ = exposure_cols.pop("max_damage_content")
    # Call the function
    dmg_suffix, dmg_idx, missing = discover_exp_columns(exposure_cols, type="damage")
    assert dmg_suffix == ["_structure"]
    assert len(dmg_idx) == 1
    assert dmg_idx[0] == [1, 3]
    assert missing == ["_content"]


def test_generate_output_columns():
    # Call the function
    new_fields = generate_output_columns(
        columns=["depth"],
        exposure_types={"damage": ["_structure"]},
        hazard_ids=[1],
    )

    # Assert the output
    assert len(new_fields) == 3
    assert new_fields[1] == "damage_structure_1"


def test_generate_output_columns_extra():
    # Call the function
    new_fields = generate_output_columns(
        columns=["depth"],
        exposure_types={"damage": ["_structure"]},
        hazard_ids=[1],
        extra=["ead"],
    )

    # Assert the output
    assert new_fields[-1] == "ead_damage"


def test_generate_output_columns_multi():
    # Call the function
    new_fields = generate_output_columns(
        columns=["depth"],
        exposure_types={"damage": ["_structure"], "affected": ["_people"]},
        hazard_ids=[1, 2],
        extra=["ead"],
    )

    # Assert the output
    assert len(new_fields) == 12
    assert new_fields[0] == "depth_1"
    assert new_fields[2] == "total_damage_1"
    assert new_fields[4] == "total_affected_1"
    assert new_fields[5] == "depth_2"
    assert new_fields[-1] == "ead_affected"
