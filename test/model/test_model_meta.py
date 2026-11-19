import shutil
from dataclasses import replace
from pathlib import Path
from typing import Callable

import netCDF4 as nc4
import numpy as np
import pytest

from fiat._core import Interp1D, InterpND
from fiat.driver import NetcdfReader
from fiat.error import FIATDataError
from fiat.model.meta import (
    ExposureGeomData,
    HazardMeta,
    RunMeta,
    VulnerabilityMeta,
    _grid_layers,
    get_exposure_geom_meta,
    get_exposure_grid_datasets,
    get_exposure_grid_meta,
    get_hazard_meta,
    get_method_types,
    get_run_meta,
    get_vulnerability_meta,
)
from fiat.settings.exposure import ExposureGridVariable
from fiat.settings.hazard import HazardVariable
from fiat.settings.vulnerability import VulnerabilityVariable


def test_get_run_meta():
    # Call the function
    meta = get_run_meta(risk=False)

    # Assert the output
    assert not meta.risk
    assert meta.cell_size == 1.0
    assert not hasattr(meta, "type")
    assert not hasattr(meta, "type_length")


def test_get_run_meta_cell_size():
    # Call the function
    meta = get_run_meta(risk=False, cell_size=25.0)

    # Assert the output
    assert meta.cell_size == 25.0


def test_get_vulnerability_meta(
    open_reader: Callable[..., NetcdfReader],
    variables,
    vulnerability_path: Path,
):
    # Call the function
    meta = get_vulnerability_meta(
        open_reader(vulnerability_path),
        [variables.vuln_1d()],
        ["default"],
    )

    # Assert the output
    assert list(meta.datasets.keys()) == ["default"]
    ds = meta.datasets["default"]
    assert ds.name == "default"
    assert ds.method == "flood.depth"
    assert ds.axis_types == ("water_depth",)
    assert ds.curve_ids == ["struct_1", "struct_2"]
    assert isinstance(ds.fn["struct_1"], Interp1D)
    assert ds.fn["struct_1"](0.0) == 0.0


def test_get_vulnerability_meta_cat(
    open_reader: Callable[..., NetcdfReader],
    variables,
    vulnerability_cat_path: Path,
):
    # Call the function
    meta = get_vulnerability_meta(
        open_reader(vulnerability_cat_path),
        [variables.vuln_1d()],
        ["default"],
    )

    # Assert the output, integer curve ids
    assert meta.datasets["default"].curve_ids == [1, 2]
    assert 1 in meta.datasets["default"].fn


def test_get_vulnerability_meta_2d(
    open_reader: Callable[..., NetcdfReader],
    variables,
    curves_2d_path: Path,
):
    # Call the function
    meta = get_vulnerability_meta(
        open_reader(curves_2d_path),
        [variables.vuln_2d()],
        ["default"],
    )

    # Assert the output
    ds = meta.datasets["default"]
    assert ds.method == "flood.depth_duration_2d"
    assert ds.axis_types == ("water_depth", "duration")
    assert isinstance(ds.fn["struct_1"], InterpND)


def test_get_vulnerability_meta_combined_order(
    open_reader: Callable[..., NetcdfReader],
    variables,
    curves_multi_path: Path,
):
    # Call the function with the datasets in a different order than the types
    meta = get_vulnerability_meta(
        open_reader(curves_multi_path),
        variables.vuln_multi(),
        ["indirect", "direct"],
    )

    # Assert the output
    assert list(meta.datasets.keys()) == ["indirect", "direct"]
    assert meta.datasets["indirect"].axis_types == ("duration",)
    assert meta.datasets["direct"].axis_types == ("water_depth",)
    assert meta.datasets["indirect"].method == "flood.depth_duration"
    assert meta.datasets["direct"].method == "flood.depth_duration"


def test_get_vulnerability_meta_override(
    open_reader: Callable[..., NetcdfReader],
    variables,
    curves_multi_path: Path,
):
    # The axis type of the settings
    variable = variables.vuln_1d(
        "indirect",
        method="flood.depth",
        index="days",
        type="water_depth",
    )

    # Call the function
    meta = get_vulnerability_meta(
        open_reader(curves_multi_path),
        [variable],
        ["indirect"],
    )

    # Assert the output
    assert meta.datasets["indirect"].axis_types == ("water_depth",)


def test_get_vulnerability_meta_ignores_file_attrs(
    open_reader: Callable[..., NetcdfReader],
    variables,
    curves_multi_path: Path,
):
    # The file says flood.depth_duration (duration axis), the settings differ
    reader = open_reader(curves_multi_path)
    assert reader.variables["indirect"].get_attr("method") == "flood.depth_duration"
    variable = variables.vuln_1d(
        "indirect",
        method="flood.level",
        index="days",
        type="water_depth",
    )

    # Call the function
    meta = get_vulnerability_meta(reader, [variable], ["indirect"])

    # Assert the settings are used
    assert meta.datasets["indirect"].method == "flood.level"
    assert meta.datasets["indirect"].axis_types == ("water_depth",)


def test_get_vulnerability_meta_unknown(
    open_reader: Callable[..., NetcdfReader],
    variables,
    vulnerability_path: Path,
):
    # Call the function with an unknown dataset
    with pytest.raises(FIATDataError, match="nope"):
        get_vulnerability_meta(
            open_reader(vulnerability_path),
            [variables.vuln_1d()],
            ["nope"],
        )


def test_get_vulnerability_meta_unlisted_dataset_raises(
    open_reader: Callable[..., NetcdfReader],
    variables,
    curves_multi_path: Path,
):
    # The dataset is in the file but has no settings
    with pytest.raises(FIATDataError, match="direct"):
        get_vulnerability_meta(
            open_reader(curves_multi_path),
            [variables.vuln_1d()],
            ["direct"],
        )


def test_get_vulnerability_meta_missing_axis_types_raises(
    open_reader: Callable[..., NetcdfReader],
    curves_2d_path: Path,
):
    # A 2D dataset with a type for one of its two index dimensions
    variable = VulnerabilityVariable(
        name="default",
        method="flood.depth_duration_2d",
        types={"depth_default": "water_depth"},
    )

    # Call the function
    with pytest.raises(FIATDataError, match="duration_default"):
        get_vulnerability_meta(open_reader(curves_2d_path), [variable], ["default"])


def test_get_vulnerability_meta_axis_type_mismatch(
    open_reader: Callable[..., NetcdfReader],
    variables,
    curves_multi_path: Path,
    vulnerability_path: Path,
):
    # A duration axis under flood.depth
    reader = open_reader(curves_multi_path)
    variable = variables.vuln_1d(
        "indirect",
        method="flood.depth",
        index="days",
        type="duration",
    )
    with pytest.raises(FIATDataError, match="indirect"):
        get_vulnerability_meta(reader, [variable], ["indirect"])

    # flood.level has a water_depth curve axis, so this passes
    reader = open_reader(vulnerability_path)
    variable = variables.vuln_1d(method="flood.level")
    meta = get_vulnerability_meta(reader, [variable], ["default"])
    assert meta.datasets["default"].method == "flood.level"
    assert meta.datasets["default"].axis_types == ("water_depth",)


def test_get_vulnerability_meta_types_unknown_dim(
    open_reader: Callable[..., NetcdfReader],
    curves_multi_path: Path,
):
    # Set the type of a dimension that is not in the dataset
    variable = VulnerabilityVariable(
        name="direct",
        method="flood.depth_duration",
        types={"nope_direct": "water_depth"},
    )
    with pytest.raises(FIATDataError, match="nope_direct"):
        get_vulnerability_meta(open_reader(curves_multi_path), [variable], ["direct"])


def test_get_vulnerability_meta_axes_not_increasing(
    open_reader: Callable[..., NetcdfReader],
    variables,
    tmp_path: Path,
    vulnerability_path: Path,
):
    # Reverse the depth axis in a copy
    p = Path(tmp_path, "curves.nc")
    shutil.copy2(vulnerability_path, p)
    with nc4.Dataset(p, "a") as ds:
        ds["depth_default"][:] = ds["depth_default"][::-1]

    # Call the function
    with pytest.raises(FIATDataError, match="depth_default"):
        get_vulnerability_meta(open_reader(p), [variables.vuln_1d()], ["default"])


def test_get_vulnerability_meta_axis_reorder(
    open_reader: Callable[..., NetcdfReader],
    variables,
    tmp_path: Path,
    curves_2d_path: Path,
):
    # Write a copy with the dataset stored as (duration, depth, curve)
    p = Path(tmp_path, "curves_2d.nc")
    with nc4.Dataset(curves_2d_path) as src, nc4.Dataset(p, "w") as dst:
        for name, dim in src.dimensions.items():
            dst.createDimension(name, len(dim))
        for name in ["depth_default", "duration_default", "curve_default"]:
            var = src[name]
            new = dst.createVariable(name, var.datatype, var.dimensions)
            new.setncatts(var.__dict__)
            new[:] = var[:]
        var = src["default"]
        new = dst.createVariable(
            "default",
            var.datatype,
            ("duration_default", "depth_default", "curve_default"),
        )
        new.setncatts(var.__dict__)
        new[:] = np.transpose(var[:], (1, 0, 2))

    # Call the function on the original and the reordered one
    org = get_vulnerability_meta(
        open_reader(curves_2d_path),
        [variables.vuln_2d()],
        ["default"],
    )
    meta = get_vulnerability_meta(open_reader(p), [variables.vuln_2d()], ["default"])

    # Assert the output
    ds = meta.datasets["default"]
    assert ds.axis_types == ("water_depth", "duration")
    for d, t in [(0.1, 0.5), (0.6, 3.0), (0.9, 7.5), (0.3, 10.0)]:
        assert ds.fn["struct_1"](d, t) == pytest.approx(
            org.datasets["default"].fn["struct_1"](d, t)
        )
        assert ds.fn["struct_2"](d, t) == pytest.approx(
            org.datasets["default"].fn["struct_2"](d, t)
        )


def test_get_method_types(
    vulnerability_meta: VulnerabilityMeta,
    vulnerability_multi_meta: VulnerabilityMeta,
):
    # A single method
    assert get_method_types(vulnerability_meta) == ["water_depth"]

    # The ordered union of the types of several methods
    assert get_method_types(vulnerability_multi_meta) == [
        "water_depth",
        "duration",
    ]

    # Ordered by the first appearance
    ds = vulnerability_multi_meta.datasets
    meta = VulnerabilityMeta(
        datasets={
            "level": replace(ds["default"], method="flood.level"),
            "default": ds["default"],
        }
    )
    assert get_method_types(meta) == ["water_level", "water_depth"]


def test_get_hazard_meta(hazard_event_data: NetcdfReader, variables):
    # Call the function
    meta = get_hazard_meta(
        hazard_event_data,
        variables.haz_event(),
        risk=False,
        method_types=["water_depth"],
    )

    # Assert the output
    assert meta.density is None
    assert meta.ids == ["1"]
    assert meta.indices_run == [[0]]
    assert meta.indices_type == [[0]]
    assert meta.rp is None
    assert meta.types == ["water_depth"]


def test_get_hazard_meta_risk(hazard_risk_data: NetcdfReader, variables):
    # Call the function
    meta = get_hazard_meta(
        hazard_risk_data,
        variables.haz_risk(),
        risk=True,
        method_types=["water_depth"],
    )

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
    assert meta.types == ["water_depth"]


def test_get_hazard_meta_multi_type(
    open_reader: Callable[..., NetcdfReader],
    variables,
    event_map_duration_path: Path,
):
    # Call the function
    meta = get_hazard_meta(
        open_reader(event_map_duration_path),
        variables.haz_event_duration(),
        risk=False,
        method_types=["water_depth", "duration"],
    )

    # Assert the output
    assert meta.ids == ["1"]
    assert meta.indices_run == [[0, 1]]
    assert meta.types == ["water_depth", "duration"]


def test_get_hazard_meta_multi_type_risk(
    open_reader: Callable[..., NetcdfReader],
    variables,
    risk_map_duration_path: Path,
):
    # Call the function
    meta = get_hazard_meta(
        open_reader(risk_map_duration_path),
        variables.haz_risk_duration(),
        risk=True,
        method_types=["water_depth", "duration"],
    )

    # Assert the output
    assert meta.ids == ["2", "5", "10", "25"]
    assert meta.indices_run == [[0, 1], [2, 3], [4, 5], [6, 7]]
    assert meta.rp == [2, 5, 10, 25]


def test_get_hazard_meta_uniform_risk(
    open_reader: Callable[..., NetcdfReader],
    variables,
    hazard_risk_path: Path,
):
    # Uniform duration layers per return period (rp as float like the settings)
    hazard = open_reader(hazard_risk_path)
    uniform = []
    for idx, rp in enumerate([2, 5, 10, 25]):
        hazard.add_constant(f"duration_{rp}", float(idx + 1))
        uniform.append(
            HazardVariable(
                name=f"duration_{rp}",
                type="duration",
                rp=float(rp),
                value=float(idx + 1),
            )
        )

    # Call the function
    meta = get_hazard_meta(
        hazard,
        variables.haz_risk() + uniform,
        risk=True,
        method_types=["water_depth", "duration"],
    )

    # Assert the output
    assert meta.ids == ["2", "5", "10", "25"]
    assert meta.indices_run == [[0, 4], [1, 5], [2, 6], [3, 7]]
    assert meta.types == ["water_depth", "duration"]
    for idx, rp in enumerate([2, 5, 10, 25]):
        band = hazard[meta.indices_run[idx][1]]
        assert band.name == f"duration_{rp}"


def test_get_hazard_meta_missing_type_rp(
    open_reader: Callable[..., NetcdfReader],
    risk_map_duration_path: Path,
):
    # Remove one duration band by giving it another type
    variables = [
        HazardVariable(
            name=f"{name}_{rp}Y",
            type="other" if (name, rp) == ("duration", 10) else type,
            rp=rp,
        )
        for rp in [2, 5, 10, 25]
        for name, type in (("depth", "water_depth"), ("duration", "duration"))
    ]

    # Call the function
    with pytest.raises(FIATDataError):
        get_hazard_meta(
            open_reader(risk_map_duration_path),
            variables,
            risk=True,
            method_types=["water_depth", "duration"],
        )


def test_get_hazard_meta_unlisted_band_ignored(
    open_reader: Callable[..., NetcdfReader],
    risk_map_duration_path: Path,
):
    # List a subset of the bands that is not first or contiguous
    hazard = open_reader(risk_map_duration_path)
    assert hazard.names[3] == "duration_5Y"
    listed = [
        HazardVariable(name="duration_5Y", type="duration", rp=5),
        HazardVariable(name="depth_25Y", type="water_depth", rp=25),
        HazardVariable(name="duration_25Y", type="duration", rp=25),
        HazardVariable(name="depth_5Y", type="water_depth", rp=5),
    ]

    # Call the function
    meta = get_hazard_meta(
        hazard,
        listed,
        risk=True,
        method_types=["water_depth", "duration"],
    )

    # Assert the indices are those of the bands in the hazard data
    assert meta.ids == ["25", "5"]
    assert meta.indices_run == [[6, 7], [2, 3]]
    assert meta.indices_type == [[6, 2], [3, 7]]


def test_get_hazard_meta_ignores_file_attrs(
    hazard_event_data: NetcdfReader,
):
    # The file says water_depth, the settings duration
    assert hazard_event_data.variables["data"].get_attr("type") == "water_depth"
    listed = [HazardVariable(name="data", type="duration")]

    # Call the function
    meta = get_hazard_meta(
        hazard_event_data,
        listed,
        risk=False,
        method_types=["duration"],
    )

    # Assert the settings are used
    assert meta.indices_run == [[0]]
    with pytest.raises(FIATDataError, match="water_depth"):
        get_hazard_meta(
            hazard_event_data,
            listed,
            risk=False,
            method_types=["water_depth"],
        )


def test_get_hazard_meta_risk_missing_rp_raises(
    hazard_risk_data: NetcdfReader,
):
    # One of the variables has no return period
    listed = [
        HazardVariable(name=name, type="water_depth", rp=None if idx == 1 else rp)
        for idx, (name, rp) in enumerate(zip(hazard_risk_data.names, [2, 5, 10, 25]))
    ]

    # Call the function
    with pytest.raises(FIATDataError, match=hazard_risk_data.names[1]):
        get_hazard_meta(
            hazard_risk_data,
            listed,
            risk=True,
            method_types=["water_depth"],
        )


def test_get_hazard_meta_unknown_variable(hazard_event_data: NetcdfReader):
    # A listed variable that is not in the hazard data
    with pytest.raises(FIATDataError, match="nope"):
        get_hazard_meta(
            hazard_event_data,
            [HazardVariable(name="nope", type="water_depth")],
            risk=False,
            method_types=["water_depth"],
        )


def test_get_exposure_geom_meta(
    exposure_geom_data_run: ExposureGeomData,
    run_meta: RunMeta,
    hazard_meta_run: HazardMeta,
    vulnerability_meta: VulnerabilityMeta,
):
    # Call the function
    meta = get_exposure_geom_meta(
        exposure=exposure_geom_data_run,
        run_meta=run_meta,
        hazard_meta=hazard_meta_run,
        vulnerability_meta=vulnerability_meta,
    )

    # Assert the output
    assert meta.area_method == "area"
    assert meta.fn is vulnerability_meta.datasets["default"].fn
    assert meta.hazard_indices == [(0,)]
    assert meta.indices_ead == {}
    assert meta.indices_impact == {"damage": [(1,)]}
    assert meta.indices_new == [5, 6, 7]
    assert meta.indices_spec == [2]
    assert meta.indices_total == {"damage": [2]}
    assert meta.indices_type == {"damage": [[3, 4]]}
    assert meta.method == "flood.depth"
    assert meta.new == ["depth_1", "damage_structure_1", "total_damage_1"]
    assert meta.new_length == 3
    assert meta.type_length == 3
    assert meta.zonal_method == "mean"


def test_get_exposure_geom_meta_2d(
    exposure_geom_data_run: ExposureGeomData,
    run_meta: RunMeta,
    hazard_meta_duration: HazardMeta,
    vulnerability_multi_meta: VulnerabilityMeta,
):
    # Call the function, like geom_2d.toml
    meta = get_exposure_geom_meta(
        exposure=replace(exposure_geom_data_run, vulnerability="default_2d"),
        run_meta=run_meta,
        hazard_meta=hazard_meta_duration,
        vulnerability_meta=vulnerability_multi_meta,
    )

    # Assert the output
    assert meta.method == "flood.depth_duration_2d"
    assert meta.fn is vulnerability_multi_meta.datasets["default_2d"].fn
    assert meta.hazard_indices == [(0, 1)]
    assert meta.indices_impact == {"damage": [(2,)]}
    assert meta.indices_total == {"damage": [3]}
    assert meta.new == [
        "depth_1",
        "duration_1",
        "damage_structure_1",
        "total_damage_1",
    ]
    assert meta.type_length == 4


def test_get_exposure_geom_meta_combined_error(
    exposure_geom_data_run: ExposureGeomData,
    run_meta: RunMeta,
    hazard_meta_duration: HazardMeta,
    vulnerability_multi_meta: VulnerabilityMeta,
):
    # A dataset of a method combining several datasets is not allowed for geom
    with pytest.raises(FIATDataError, match="direct"):
        get_exposure_geom_meta(
            exposure=replace(exposure_geom_data_run, vulnerability="direct"),
            run_meta=run_meta,
            hazard_meta=hazard_meta_duration,
            vulnerability_meta=vulnerability_multi_meta,
        )


def test_get_exposure_geom_meta_unknown_curve(
    exposure_geom_data_run: ExposureGeomData,
    run_meta: RunMeta,
    hazard_meta_run: HazardMeta,
    vulnerability_meta: VulnerabilityMeta,
):
    # Remove a curve used by the exposure from the linked dataset
    ds = vulnerability_meta.datasets["default"]
    ds = replace(ds, curve_ids=["struct_1"], fn={"struct_1": ds.fn["struct_1"]})

    # Call the function
    with pytest.raises(FIATDataError, match="struct_2"):
        get_exposure_geom_meta(
            exposure=exposure_geom_data_run,
            run_meta=run_meta,
            hazard_meta=hazard_meta_run,
            vulnerability_meta=VulnerabilityMeta(datasets={"default": ds}),
        )


def test_get_exposure_geom_meta_unknown_dataset(
    exposure_geom_data_run: ExposureGeomData,
    run_meta: RunMeta,
    hazard_meta_run: HazardMeta,
    vulnerability_meta: VulnerabilityMeta,
):
    # Call the function
    with pytest.raises(FIATDataError, match="unknown"):
        get_exposure_geom_meta(
            exposure=replace(exposure_geom_data_run, vulnerability="unknown"),
            run_meta=run_meta,
            hazard_meta=hazard_meta_run,
            vulnerability_meta=vulnerability_meta,
        )


def test_get_exposure_geom_meta_risk_depth(
    exposure_geom_data_run: ExposureGeomData,
    run_risk_meta: RunMeta,
    hazard_risk_meta_run: HazardMeta,
    vulnerability_meta: VulnerabilityMeta,
):
    meta = get_exposure_geom_meta(
        exposure=exposure_geom_data_run,
        run_meta=run_risk_meta,
        hazard_meta=hazard_risk_meta_run,
        vulnerability_meta=vulnerability_meta,
    )

    # Assert the output
    assert meta.hazard_indices == [(0,), (1,), (2,), (3,)]
    assert meta.indices_ead == {"damage": 12}
    assert meta.indices_impact == {"damage": [(1,), (4,), (7,), (10,)]}
    assert meta.indices_new == list(range(5, 18, 1))
    assert meta.indices_spec == [2]
    assert meta.indices_total == {"damage": [2, 5, 8, 11]}
    assert meta.indices_type == {"damage": [[3, 4]]}
    assert "depth_2" in meta.new
    assert "total_damage_5" in meta.new
    assert meta.new[-1] == "ead"
    assert meta.new_length == 13
    assert meta.type_length == 3


def test_get_exposure_geom_meta_risk(
    exposure_geom_types_data_run: ExposureGeomData,
    run_risk_meta: RunMeta,
    variables,
    risk_map_duration_path: Path,
    vulnerability_multi_meta: VulnerabilityMeta,
):
    # Like geom_2d_risk.toml
    with NetcdfReader(risk_map_duration_path) as hazard:
        hazard_meta = get_hazard_meta(
            hazard,
            variables.haz_risk_duration(),
            risk=True,
            method_types=["water_depth", "duration"],
        )
    meta = get_exposure_geom_meta(
        exposure=exposure_geom_types_data_run,
        run_meta=run_risk_meta,
        hazard_meta=hazard_meta,
        vulnerability_meta=vulnerability_multi_meta,
    )

    # Assert the output, two hazard columns per return period
    assert meta.hazard_indices == [(0, 1), (2, 3), (4, 5), (6, 7)]
    assert meta.type_length == 6
    assert meta.new[:6] == [
        "depth_2",
        "duration_2",
        "damage_structure_2",
        "total_damage_2",
        "affected_structure_2",
        "total_affected_2",
    ]
    assert meta.indices_impact == {
        "damage": [(2,), (8,), (14,), (20,)],
        "affected": [(4,), (10,), (16,), (22,)],
    }
    assert meta.indices_total == {
        "damage": [3, 9, 15, 21],
        "affected": [5, 11, 17, 23],
    }
    assert len(meta.indices_total["damage"]) == 4
    assert len(meta.indices_total["affected"]) == 4
    assert meta.new_length == 26


def test_get_exposure_geom_meta_risk_types(
    exposure_geom_types_data_run: ExposureGeomData,
    run_risk_meta: RunMeta,
    hazard_risk_meta_run: HazardMeta,
    vulnerability_meta: VulnerabilityMeta,
):
    # Two impact types, one ead column per type
    meta = get_exposure_geom_meta(
        exposure=replace(exposure_geom_types_data_run, vulnerability="default"),
        run_meta=run_risk_meta,
        hazard_meta=hazard_risk_meta_run,
        vulnerability_meta=vulnerability_meta,
    )

    # Assert the output
    assert meta.new[-2:] == ["ead_damage", "ead_affected"]
    assert meta.indices_ead == {"damage": 20, "affected": 21}
    assert meta.new_length == 22

    # One impact type, a single ead column
    meta = get_exposure_geom_meta(
        exposure=replace(
            exposure_geom_types_data_run,
            impact_types=["affected"],
            vulnerability="default",
        ),
        run_meta=run_risk_meta,
        hazard_meta=hazard_risk_meta_run,
        vulnerability_meta=vulnerability_meta,
    )

    # Assert the output
    assert meta.new[-1] == "ead"
    assert "ead_affected" not in meta.new
    assert meta.indices_ead == {"affected": meta.new_length - 1}


def test_get_exposure_grid_datasets(
    variables,
    exposure_grid_data: NetcdfReader,
    exposure_grid_combined_data: NetcdfReader,
    exposure_grid_cat_data: NetcdfReader,
    exposure_grid_cat_variables_data: NetcdfReader,
):
    # Only the default
    assert get_exposure_grid_datasets(
        exposure_grid_data,
        variables.exp_grid(),
    ) == ["default"]
    # Layer links from the settings, the default first via exposure1
    assert get_exposure_grid_datasets(
        exposure_grid_combined_data,
        variables.exp_grid_combined(),
    ) == ["default", "direct", "indirect"]
    # Categorized, the links of the category value variables
    assert get_exposure_grid_datasets(
        exposure_grid_cat_data,
        variables.exp_cat_default(),
    ) == ["default"]
    # Different links per category value variable
    assert get_exposure_grid_datasets(
        exposure_grid_cat_variables_data,
        variables.exp_cat_variables(),
    ) == ["default", "default_2d"]


def test_get_exposure_grid_datasets_ignores_file_attrs(
    open_reader: Callable[..., NetcdfReader],
    variables,
    tmp_path: Path,
    exposure_grid_path: Path,
):
    # Copy of the exposure with a link set as a netcdf attribute
    p = Path(tmp_path, "spatial.nc")
    shutil.copy2(exposure_grid_path, p)
    with nc4.Dataset(p, "a") as ds:
        ds["exposure2"].setncattr("vulnerability", "default_2d")

    # The attribute is not used, the settings are
    assert get_exposure_grid_datasets(
        open_reader(p),
        variables.exp_grid(),
    ) == ["default"]
    assert get_exposure_grid_datasets(
        open_reader(p),
        variables.exp_grid(exposure2="direct"),
    ) == ["default", "direct"]


def test_grid_layers_unlisted_variable_ignored(
    variables,
    exposure_grid_data: NetcdfReader,
):
    # Only list the second layer
    listed = variables.exp_grid()[1:]

    # Call the function
    layers = _grid_layers(exposure_grid_data, listed)

    # Assert the layer index is the one of the exposure data
    assert layers == [(1, None, ["default"])]


def test_grid_layers_ignores_file_attrs(
    variables,
    exposure_grid_data: NetcdfReader,
):
    # The file says exposure1 is of type 'default' with curve 'struct_1'
    assert exposure_grid_data.variables["exposure1"].get_attr("type") == "default"

    # The settings say it is categorized (value variables by dimension: none)
    listed = [
        ExposureGridVariable(
            name="exposure1", type="categorized", values=["exposure2"]
        ),
        ExposureGridVariable(name="exposure2", type="values", vulnerability="default"),
    ]
    layers = _grid_layers(exposure_grid_data, listed)

    # Assert the settings are used
    assert layers == [(0, 1, ["default"])]


def test_grid_layers_no_layers(variables, exposure_grid_data: NetcdfReader):
    # Nothing listed that is a layer
    with pytest.raises(FIATDataError, match="No exposure layers"):
        _grid_layers(
            exposure_grid_data,
            [
                ExposureGridVariable(
                    name="exposure1", type="values", vulnerability="default"
                )
            ],
        )


def test_grid_layers_unknown_variable(variables, exposure_grid_data: NetcdfReader):
    # A listed layer that is not in the exposure data
    with pytest.raises(FIATDataError, match="nope"):
        _grid_layers(
            exposure_grid_data,
            [
                ExposureGridVariable(
                    name="nope",
                    type="default",
                    fn_curve="struct_1",
                    vulnerability="default",
                )
            ],
        )


def test_get_exposure_grid_meta(
    variables,
    exposure_grid_data: NetcdfReader,
    run_meta: RunMeta,
    hazard_meta_run: HazardMeta,
    vulnerability_meta: VulnerabilityMeta,
):
    # Call the function
    meta = get_exposure_grid_meta(
        exposure=exposure_grid_data,
        variables=variables.exp_grid(),
        run_meta=run_meta,
        hazard_meta=hazard_meta_run,
        vulnerability_meta=vulnerability_meta,
    )

    # Assert the output
    assert meta.new == ["exposure1_1", "exposure2_1", "total_1"]
    assert meta.nb == 3
    assert meta.index_ead is None
    assert meta.indices_total == [2]
    assert meta.totals == [[0, 1]]
    assert len(meta.units) == 2
    unit = meta.units[0]
    assert unit.method == "flood.depth"
    assert unit.exp_index == 0
    assert unit.hazard_indices == [(0,)]
    assert unit.out_indices == [0]
    assert unit.value_index is None
    assert unit.curves == (vulnerability_meta.datasets["default"].fn["struct_1"],)
    assert (
        meta.units[1].curves[0] is vulnerability_meta.datasets["default"].fn["struct_2"]
    )


def test_get_exposure_grid_meta_combined(
    variables,
    exposure_grid_combined_data: NetcdfReader,
    run_meta: RunMeta,
    hazard_meta_duration: HazardMeta,
    vulnerability_multi_meta: VulnerabilityMeta,
):
    # Call the function
    meta = get_exposure_grid_meta(
        exposure=exposure_grid_combined_data,
        variables=variables.exp_grid_combined(),
        run_meta=run_meta,
        hazard_meta=hazard_meta_duration,
        vulnerability_meta=vulnerability_multi_meta,
    )

    # Assert the output, one combined unit for exposure2
    assert meta.new == ["exposure1_1", "exposure2_1", "total_1"]
    units = [item for item in meta.units if item.exp_index == 1]
    assert len(units) == 1
    unit = units[0]
    assert unit.method == "flood.depth_duration"
    assert len(unit.curves) == 2
    ds = vulnerability_multi_meta.datasets
    assert unit.curves[0] is ds["direct"].fn["struct_2"]
    assert unit.curves[1] is ds["indirect"].fn["struct_2"]
    assert unit.hazard_indices == [(0, 1)]
    assert meta.units[0].hazard_indices == [(0,)]
    assert meta.totals == [[0, 1]]


def test_get_exposure_grid_meta_combined_order(
    open_reader: Callable[..., NetcdfReader],
    variables,
    exposure_grid_path: Path,
    run_meta: RunMeta,
    hazard_meta_duration: HazardMeta,
    vulnerability_multi_meta: VulnerabilityMeta,
):
    # Datasets listed in reverse order
    exposure = open_reader(exposure_grid_path)

    # Call the function
    meta = get_exposure_grid_meta(
        exposure=exposure,
        variables=variables.exp_grid(exposure2=["indirect", "direct"]),
        run_meta=run_meta,
        hazard_meta=hazard_meta_duration,
        vulnerability_meta=vulnerability_multi_meta,
    )

    # Assert the output, ordered by axis type
    ds = vulnerability_multi_meta.datasets
    assert meta.units[1].curves[0] is ds["direct"].fn["struct_2"]
    assert meta.units[1].curves[1] is ds["indirect"].fn["struct_2"]
    assert meta.new[1] == "exposure2_1"


def test_get_exposure_grid_meta_separate(
    variables,
    exposure_grid_separate_data: NetcdfReader,
    run_meta: RunMeta,
    hazard_meta_duration: HazardMeta,
    vulnerability_multi_meta: VulnerabilityMeta,
):
    # Call the function
    meta = get_exposure_grid_meta(
        exposure=exposure_grid_separate_data,
        variables=variables.exp_grid_separate(),
        run_meta=run_meta,
        hazard_meta=hazard_meta_duration,
        vulnerability_meta=vulnerability_multi_meta,
    )

    # Assert the output, two units for exposure2
    assert meta.new == [
        "exposure1_1",
        "exposure2_default_1",
        "exposure2_default_2d_1",
        "total_1",
    ]
    units = [item for item in meta.units if item.exp_index == 1]
    assert len(units) == 2
    assert [item.method for item in units] == [
        "flood.depth",
        "flood.depth_duration_2d",
    ]
    assert units[1].hazard_indices == [(0, 1)]
    out = [item.out_indices[0] for item in units]
    assert out == [1, 2]
    assert meta.totals == [[0, 1, 2]]
    assert meta.indices_total == [3]


def test_get_exposure_grid_meta_combined_duplicate_type(
    variables,
    exposure_grid_combined_data: NetcdfReader,
    run_meta: RunMeta,
    hazard_meta_duration: HazardMeta,
    vulnerability_multi_meta: VulnerabilityMeta,
):
    # Both datasets of the combined group are of the water_depth type, like a
    # types={"days_indirect": "water_depth"} spec on 'indirect' (not reopening the
    # curves file, see test_get_vulnerability_meta_override for the spec itself)
    ds = vulnerability_multi_meta.datasets
    vuln = VulnerabilityMeta(
        datasets={
            **ds,
            "indirect": replace(ds["indirect"], axis_types=("water_depth",)),
        }
    )

    # Call the function
    with pytest.raises(FIATDataError, match="duplicate axis types"):
        get_exposure_grid_meta(
            exposure=exposure_grid_combined_data,
            variables=variables.exp_grid_combined(),
            run_meta=run_meta,
            hazard_meta=hazard_meta_duration,
            vulnerability_meta=vuln,
        )


def test_get_exposure_grid_meta_cat(
    variables,
    exposure_grid_cat_data: NetcdfReader,
    run_meta: RunMeta,
    hazard_meta_run: HazardMeta,
    vulnerability_cat_meta: VulnerabilityMeta,
):
    # Call the function
    meta = get_exposure_grid_meta(
        exposure=exposure_grid_cat_data,
        variables=variables.exp_cat_default(),
        run_meta=run_meta,
        hazard_meta=hazard_meta_run,
        vulnerability_meta=vulnerability_cat_meta,
    )

    # Assert the output, two category value variables found via the dimension
    names = exposure_grid_cat_data.names
    assert meta.new == ["exposure_values_1", "exposure_values2_1", "total_1"]
    assert len(meta.units) == 2
    for unit, value in zip(meta.units, ["exposure_values", "exposure_values2"]):
        assert unit.exp_index == names.index("exposure")
        assert unit.value_index == names.index(value)
        assert list(unit.curves.keys()) == [1, 2]
        assert unit.curves[1] == (vulnerability_cat_meta.datasets["default"].fn[1],)
    assert meta.totals == [[0, 1]]


def test_get_exposure_grid_meta_cat_links(
    variables,
    exposure_grid_cat_variables_data: NetcdfReader,
    run_meta: RunMeta,
    hazard_meta_duration: HazardMeta,
    vulnerability_cat_meta: VulnerabilityMeta,
):
    # Call the function, the category value variables have different links
    meta = get_exposure_grid_meta(
        exposure=exposure_grid_cat_variables_data,
        variables=variables.exp_cat_variables(),
        run_meta=run_meta,
        hazard_meta=hazard_meta_duration,
        vulnerability_meta=vulnerability_cat_meta,
    )

    # Assert the output
    ds = vulnerability_cat_meta.datasets
    names = exposure_grid_cat_variables_data.names
    assert len(meta.units) == 2
    unit1, unit2 = meta.units
    assert unit1.value_index == names.index("exposure_values")
    assert unit1.method == "flood.depth"
    assert unit1.curves[2] == (ds["default"].fn[2],)
    assert unit2.value_index == names.index("exposure_values2")
    assert unit2.method == "flood.depth_duration_2d"
    assert unit2.curves[2] == (ds["default_2d"].fn[2],)
    assert unit2.hazard_indices == [(0, 1)]


def test_get_exposure_grid_meta_cat_names(
    variables,
    exposure_grid_cat_variables_data: NetcdfReader,
    run_meta: RunMeta,
    hazard_meta_duration: HazardMeta,
    vulnerability_cat_meta: VulnerabilityMeta,
):
    # Call the function
    meta = get_exposure_grid_meta(
        exposure=exposure_grid_cat_variables_data,
        variables=variables.exp_cat_variables(),
        run_meta=run_meta,
        hazard_meta=hazard_meta_duration,
        vulnerability_meta=vulnerability_cat_meta,
    )

    # Assert the output
    assert "exposure_values_1" in meta.new
    assert "exposure_values2_1" in meta.new
    assert meta.new[-1] == "total_1"


def test_get_exposure_grid_meta_cat_several_units(
    open_reader: Callable[..., NetcdfReader],
    variables,
    exposure_grid_cat_path: Path,
    run_meta: RunMeta,
    hazard_meta_duration: HazardMeta,
    vulnerability_cat_meta: VulnerabilityMeta,
):
    # One value variable linked to two separate datasets
    exposure = open_reader(exposure_grid_cat_path)
    listed = [
        variables.exp_cat(values=["exposure_values"]),
        ExposureGridVariable(
            name="exposure_values",
            type="values",
            vulnerability=["default", "default_2d"],
        ),
    ]

    # Call the function
    meta = get_exposure_grid_meta(
        exposure=exposure,
        variables=listed,
        run_meta=run_meta,
        hazard_meta=hazard_meta_duration,
        vulnerability_meta=vulnerability_cat_meta,
    )

    # Assert the output
    assert meta.new == [
        "exposure_values_default_1",
        "exposure_values_default_2d_1",
        "total_1",
    ]


def test_get_exposure_grid_meta_cat_uniform(
    variables,
    exposure_grid_cat_uniform_data: NetcdfReader,
    run_meta: RunMeta,
    hazard_meta_duration: HazardMeta,
    vulnerability_cat_meta: VulnerabilityMeta,
):
    # Call the function
    meta = get_exposure_grid_meta(
        exposure=exposure_grid_cat_uniform_data,
        variables=variables.exp_cat_uniform(),
        run_meta=run_meta,
        hazard_meta=hazard_meta_duration,
        vulnerability_meta=vulnerability_cat_meta,
    )

    # Assert the output
    names = exposure_grid_cat_uniform_data.names
    assert meta.new == ["exposure_values2_1", "exposure_values_1", "total_1"]
    unit = meta.units[1]
    assert unit.exp_index == names.index("exposure_uniform")
    assert unit.value_index == names.index("exposure_values")
    assert list(unit.curves.keys()) == [1, 2]


def test_get_exposure_grid_meta_cat_missing_category(
    variables,
    open_reader: Callable[..., NetcdfReader],
    tmp_path: Path,
    vulnerability_cat_path: Path,
    exposure_grid_cat_path: Path,
    run_meta: RunMeta,
    hazard_meta_run: HazardMeta,
    vulnerability_cat_meta: VulnerabilityMeta,
):
    # Copy of the curves without curve id 2
    p = Path(tmp_path, "curves_cat.nc")
    shutil.copy2(vulnerability_cat_path, p)
    with nc4.Dataset(p, "a") as ds:
        ds["curve_default"][:] = [1, 3]
    vuln = get_vulnerability_meta(open_reader(p), [variables.vuln_1d()], ["default"])

    # Uniform categorized layer with a category not in the dataset
    exposure = open_reader(exposure_grid_cat_path)
    exposure.add_constant("exposure_uniform", 7)
    listed = [
        variables.exp_cat(values=["exposure_values2"]),
        ExposureGridVariable(
            name="exposure_uniform",
            type="categorized",
            value=7,
            values=["exposure_values"],
        ),
        *variables.exp_values(),
    ]
    with pytest.raises(FIATDataError, match=r"Category 7 .* not in the categories"):
        get_exposure_grid_meta(
            exposure=exposure,
            variables=listed,
            run_meta=run_meta,
            hazard_meta=hazard_meta_run,
            vulnerability_meta=vulnerability_cat_meta,
        )

    # Also when the dataset itself does have a curve for that category
    ds = vulnerability_cat_meta.datasets["default"]
    vuln = VulnerabilityMeta(
        datasets={
            "default": replace(
                ds,
                curve_ids=ds.curve_ids + [7],
                fn={**ds.fn, 7: ds.fn[1]},
            )
        }
    )
    with pytest.raises(FIATDataError, match=r"Category 7 .* not in the categories"):
        get_exposure_grid_meta(
            exposure=exposure,
            variables=listed,
            run_meta=run_meta,
            hazard_meta=hazard_meta_run,
            vulnerability_meta=vuln,
        )


def test_get_exposure_grid_meta_cat_uniform_no_category_dim(
    open_reader: Callable[..., NetcdfReader],
    variables,
    exposure_grid_cat_path: Path,
    run_meta: RunMeta,
    hazard_meta_run: HazardMeta,
    vulnerability_cat_meta: VulnerabilityMeta,
):
    # Uniform categorized layer with a (spatial) value variable without a single
    # category dimension
    exposure = open_reader(exposure_grid_cat_path)
    exposure.add_constant("exposure_uniform", 1)
    listed = [
        ExposureGridVariable(
            name="exposure_uniform",
            type="categorized",
            value=1,
            values=["exposure"],
        ),
        ExposureGridVariable(name="exposure", type="values", vulnerability="default"),
    ]
    with pytest.raises(FIATDataError, match="no single category dimension"):
        get_exposure_grid_meta(
            exposure=exposure,
            variables=listed,
            run_meta=run_meta,
            hazard_meta=hazard_meta_run,
            vulnerability_meta=vulnerability_cat_meta,
        )


def test_get_exposure_grid_meta_cat_values_not_in_settings(
    open_reader: Callable[..., NetcdfReader],
    variables,
    exposure_grid_cat_path: Path,
    run_meta: RunMeta,
    hazard_meta_run: HazardMeta,
    vulnerability_cat_meta: VulnerabilityMeta,
):
    exposure = open_reader(exposure_grid_cat_path)

    # Category value variables (discovered) without an entry in the settings
    with pytest.raises(FIATDataError, match="exposure_values.*type 'values'"):
        get_exposure_grid_meta(
            exposure=exposure,
            variables=[variables.exp_cat()],
            run_meta=run_meta,
            hazard_meta=hazard_meta_run,
            vulnerability_meta=vulnerability_cat_meta,
        )

    # Only one of the set category value variables has an entry
    with pytest.raises(FIATDataError, match="exposure_values2"):
        get_exposure_grid_meta(
            exposure=exposure,
            variables=[
                variables.exp_cat(values=["exposure_values", "exposure_values2"]),
                *variables.exp_values("exposure_values"),
            ],
            run_meta=run_meta,
            hazard_meta=hazard_meta_run,
            vulnerability_meta=vulnerability_cat_meta,
        )

    # An entry that is not of type 'values'
    with pytest.raises(FIATDataError, match="exposure_values"):
        get_exposure_grid_meta(
            exposure=exposure,
            variables=[
                variables.exp_cat(values=["exposure_values"]),
                ExposureGridVariable(
                    name="exposure_values",
                    type="default",
                    fn_curve=1,
                    vulnerability="default",
                ),
            ],
            run_meta=run_meta,
            hazard_meta=hazard_meta_run,
            vulnerability_meta=vulnerability_cat_meta,
        )


def test_get_exposure_grid_meta_cat_values_missing(
    open_reader: Callable[..., NetcdfReader],
    variables,
    exposure_grid_cat_path: Path,
    run_meta: RunMeta,
    hazard_meta_run: HazardMeta,
    vulnerability_cat_meta: VulnerabilityMeta,
):
    # Unknown category value variable
    exposure = open_reader(exposure_grid_cat_path)

    # Call the function
    with pytest.raises(FIATDataError, match="nope"):
        get_exposure_grid_meta(
            exposure=exposure,
            variables=[variables.exp_cat(values=["nope"])],
            run_meta=run_meta,
            hazard_meta=hazard_meta_run,
            vulnerability_meta=vulnerability_cat_meta,
        )


def test_get_exposure_grid_meta_cat_value_uniform(
    open_reader: Callable[..., NetcdfReader],
    variables,
    exposure_grid_cat_path: Path,
    run_meta: RunMeta,
    hazard_meta_run: HazardMeta,
    vulnerability_cat_meta: VulnerabilityMeta,
):
    # A category value variable defined by a value
    exposure = open_reader(exposure_grid_cat_path)
    exposure.add_constant("exposure_const", 5.0)
    listed = [
        variables.exp_cat(values=["exposure_values", "exposure_const"]),
        ExposureGridVariable(
            name="exposure_const",
            type="default",
            fn_curve=1,
            vulnerability="default",
            value=5.0,
        ),
    ]
    with pytest.raises(FIATDataError, match="can't be uniform layers"):
        get_exposure_grid_meta(
            exposure=exposure,
            variables=listed,
            run_meta=run_meta,
            hazard_meta=hazard_meta_run,
            vulnerability_meta=vulnerability_cat_meta,
        )

    # A category value variable shared by two categorized layers
    exposure = open_reader(exposure_grid_cat_path)
    exposure.add_constant("exposure_uniform", 1)
    listed = [
        variables.exp_cat(),
        ExposureGridVariable(
            name="exposure_uniform",
            type="categorized",
            value=1,
            values=["exposure_values"],
        ),
    ]
    with pytest.raises(FIATDataError, match="is shared between"):
        get_exposure_grid_meta(
            exposure=exposure,
            variables=listed,
            run_meta=run_meta,
            hazard_meta=hazard_meta_run,
            vulnerability_meta=vulnerability_cat_meta,
        )


def test_get_exposure_grid_meta_level_error(
    variables,
    exposure_grid_data: NetcdfReader,
    run_meta: RunMeta,
    hazard_meta_run: HazardMeta,
    vulnerability_meta: VulnerabilityMeta,
):
    # Method needing a hazard conversion, like method="flood.level" on 'default'
    # (see test_get_vulnerability_meta_axis_type_mismatch)
    vuln = VulnerabilityMeta(
        datasets={
            "default": replace(
                vulnerability_meta.datasets["default"], method="flood.level"
            )
        }
    )

    # Call the function
    with pytest.raises(FIATDataError, match="flood.level"):
        get_exposure_grid_meta(
            exposure=exposure_grid_data,
            variables=variables.exp_grid(),
            run_meta=run_meta,
            hazard_meta=hazard_meta_run,
            vulnerability_meta=vuln,
        )


def test_get_exposure_grid_meta_unknown_curve(
    open_reader: Callable[..., NetcdfReader],
    exposure_grid_path: Path,
    run_meta: RunMeta,
    hazard_meta_run: HazardMeta,
    vulnerability_meta: VulnerabilityMeta,
):
    # Curve not in the linked dataset
    exposure = open_reader(exposure_grid_path)
    listed = [
        ExposureGridVariable(
            name="exposure1",
            type="default",
            fn_curve="nope",
            vulnerability="default",
        )
    ]

    # Call the function
    with pytest.raises(FIATDataError, match="nope"):
        get_exposure_grid_meta(
            exposure=exposure,
            variables=listed,
            run_meta=run_meta,
            hazard_meta=hazard_meta_run,
            vulnerability_meta=vulnerability_meta,
        )


def test_get_exposure_grid_meta_unknown_dataset(
    variables,
    exposure_grid_data: NetcdfReader,
    run_meta: RunMeta,
    hazard_meta_run: HazardMeta,
    vulnerability_meta: VulnerabilityMeta,
):
    # Link to a dataset that is not loaded
    with pytest.raises(FIATDataError, match="nope"):
        get_exposure_grid_meta(
            exposure=exposure_grid_data,
            variables=variables.exp_grid(default="nope"),
            run_meta=run_meta,
            hazard_meta=hazard_meta_run,
            vulnerability_meta=vulnerability_meta,
        )


def test_get_exposure_grid_meta_risk(
    variables,
    exposure_grid_data: NetcdfReader,
    run_risk_meta: RunMeta,
    hazard_risk_meta_run: HazardMeta,
    vulnerability_meta: VulnerabilityMeta,
):
    # Call the function
    meta = get_exposure_grid_meta(
        exposure=exposure_grid_data,
        variables=variables.exp_grid(),
        run_meta=run_risk_meta,
        hazard_meta=hazard_risk_meta_run,
        vulnerability_meta=vulnerability_meta,
    )

    # Assert the output
    assert meta.index_ead == len(meta.new) - 1
    assert meta.index_ead == 12
    assert meta.nb == 13
    assert len(meta.indices_total) == 4
    assert meta.indices_total == [8, 9, 10, 11]
    assert meta.units[0].out_indices == [0, 1, 2, 3]
    assert meta.units[1].out_indices == [4, 5, 6, 7]
    assert meta.units[0].hazard_indices == [(0,), (1,), (2,), (3,)]
    assert meta.totals == [[0, 4], [1, 5], [2, 6], [3, 7]]
    assert "exposure1_5" in meta.new
    assert "exposure2_10" in meta.new
    assert "total_25" in meta.new
    assert meta.new[-1] == "ead"
