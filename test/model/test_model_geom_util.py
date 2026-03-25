from pathlib import Path

from fiat.fio import GeomIO
from fiat.method import flood
from fiat.model.geom_util import (
    discover_exp_columns,
    generate_output_columns,
    generate_output_filepaths,
    get_exposure_meta,
)
from fiat.struct.container import HazardMeta, RunMeta


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


def test_generate_output_filepaths(
    tmp_path: Path,
):
    # Call the function
    out = generate_output_filepaths(
        outfiles=["foo.gpkg", "bar.gpkg"],
        infiles=[],
        output_dir=tmp_path,
    )

    # Assert the output
    assert len(out) == 2
    assert out[0] == Path(tmp_path, "foo.gpkg")


def test_generate_output_filepaths_none(
    tmp_path: Path,
):
    # Call the function
    out = generate_output_filepaths(
        outfiles=None,
        infiles=["foo.gpkg"],
        output_dir=tmp_path,
    )

    # Assert the output
    assert len(out) == 1
    assert out[0] == Path(tmp_path, "foo.gpkg")


def test_generate_output_filepaths_add(
    tmp_path: Path,
):
    # Call the function
    out = generate_output_filepaths(
        outfiles=["foo.gpkg"],
        infiles=["baz.gpkg", "bar.gpkg"],
        output_dir=tmp_path,
    )

    # Assert the output
    assert len(out) == 2
    assert out[0] == Path(tmp_path, "foo.gpkg")
    assert out[1] == Path(tmp_path, "bar.gpkg")


def test_get_exposure_meta(
    exposure_geom_data: GeomIO,
    run_meta: RunMeta,
    hazard_meta_run: HazardMeta,
):
    # Call the function
    meta = get_exposure_meta(
        exposure=exposure_geom_data,
        run_meta=run_meta,
        hazard_meta=hazard_meta_run,
        method=flood.depth,
        types=["damage"],
    )

    # Assert the output
    assert meta.indices_impact == {"damage": [(1,)]}
    assert meta.indices_new == [5, 6, 7]
    assert meta.indices_spec == [2]
    assert meta.indices_total == {"damage": [2]}
    assert meta.indices_type == {"damage": [[3, 4]]}
    assert meta.new == ["depth_1", "damage_structure_1", "total_damage_1"]
    assert meta.new_length == 3
    assert meta.type_length == 3


def test_get_exposure_meta_risk(
    exposure_geom_data: GeomIO,
    run_risk_meta: RunMeta,
    hazard_risk_meta_run: HazardMeta,
):
    meta = get_exposure_meta(
        exposure=exposure_geom_data,
        run_meta=run_risk_meta,
        hazard_meta=hazard_risk_meta_run,
        method=flood.depth,
        types=["damage"],
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
