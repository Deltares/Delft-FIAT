import math
import shutil
from dataclasses import replace
from multiprocessing import get_context
from pathlib import Path
from typing import Callable

import netCDF4 as nc4
import numpy as np

from fiat.driver import FlatGeobufReader, NetcdfReader, fgb
from fiat.gis import overlay
from fiat.method import flood
from fiat.method.ead import fn_ead
from fiat.method.flood.depth import fn_hazard, fn_impact
from fiat.model.geom_worker import feature_worker, initialize_pool, worker
from fiat.model.meta import (
    ExposureGeomData,
    ExposureGeomMeta,
    HazardMeta,
    RunMeta,
    VulnerabilityMeta,
    get_exposure_geom_meta,
    get_hazard_meta,
)
from fiat.open import open_geom
from fiat.settings.variables import HazardVariable


def _feature_by_id(layer, object_id):
    """Return the feature with a given object_id (order-independent)."""
    for ft in layer:
        if ft.get_field("object_id") == object_id:
            return ft
    raise AssertionError(f"No feature with object_id={object_id}")


def test_feature_worker(
    run_meta: RunMeta,
    hazard_event_data: NetcdfReader,
    hazard_meta_run: HazardMeta,
    exposure_geom_data: FlatGeobufReader,
    exposure_geom_meta_run: ExposureGeomMeta,
):
    # Create the array
    out_array = np.zeros(exposure_geom_meta_run.new_length, dtype=np.float32)

    # Call the function
    feature_worker(
        ft=_feature_by_id(exposure_geom_data, 1),
        out_array=out_array,
        run_meta=run_meta,
        hazard=hazard_event_data,
        hazard_meta=hazard_meta_run,
        exposure_meta=exposure_geom_meta_run,
        fn_hazard=fn_hazard,
        fn_impact=fn_impact,
    )

    # Assert the output
    np.testing.assert_array_almost_equal(out_array, [3.4, 760, 760], decimal=2)


def test_feature_worker_risk(
    run_risk_meta: RunMeta,
    hazard_risk_data: NetcdfReader,
    hazard_risk_meta_run: HazardMeta,
    exposure_geom_data: FlatGeobufReader,
    exposure_geom_risk_meta_run: ExposureGeomMeta,
):
    # Create the array
    out_array = np.zeros(exposure_geom_risk_meta_run.new_length, dtype=np.float32)

    # Call the function
    feature_worker(
        ft=_feature_by_id(exposure_geom_data, 3),
        out_array=out_array,
        run_meta=run_risk_meta,
        hazard=hazard_risk_data,
        hazard_meta=hazard_risk_meta_run,
        exposure_meta=exposure_geom_risk_meta_run,
        fn_hazard=fn_hazard,
        fn_impact=fn_impact,
    )

    # Assert the output
    assert len(out_array) == (
        exposure_geom_risk_meta_run.type_length * hazard_risk_data.size + 1
    )
    np.testing.assert_almost_equal(out_array[0], 2.61, decimal=2)
    np.testing.assert_almost_equal(out_array[2], 1792.3, decimal=1)
    np.testing.assert_almost_equal(out_array[6], 3.31, decimal=2)
    np.testing.assert_almost_equal(out_array[10], 2279.1, decimal=1)
    np.testing.assert_almost_equal(out_array[-1], 1022.7, decimal=1)


def _finalize(key: str, records: list, exposure: FlatGeobufReader, new: list):
    """Finalize a worker output file (as the parent model would)."""
    profile = exposure.profile
    fgb.finalize(
        key,
        f"{key}.body",
        Path(key).stem,
        profile.geom_type,
        list(profile.fields) + list(new),
        list(profile.dtypes) + [fgb.CT_DOUBLE] * len(new),
        records,
        crs_wkt=profile.crs_wkt,
        crs_org=profile.crs_org,
        crs_code=profile.crs_code,
    )


def _depth_duration(
    hazard: NetcdfReader,
    ft,
    indices: tuple[int, int],
) -> tuple[float, float, float]:
    """Return the (area) mean depth and wet duration and the reduction factor."""
    mask, window = overlay.area_mask(
        geom=ft.geometry,
        gtf=hazard.profile.transform,
        shape=hazard.profile.shape_xy,
    )
    depths = overlay.clip(hazard[indices[0]], mask, window)
    durations = overlay.clip(hazard[indices[1]], mask, window)
    (depth,), fact = flood.depth.fn_hazard((depths,), 0.0)
    duration = float(np.mean(durations[depths > 0]))
    return depth, duration, fact


def test_worker(
    tmp_path: Path,
    run_meta: RunMeta,
    hazard_event_data: NetcdfReader,
    hazard_meta_run: HazardMeta,
    exposure_geom_data: FlatGeobufReader,
    exposure_geom_meta_run: ExposureGeomMeta,
):
    # Setup the worker globals (lock + pipeline queue)
    ctx = get_context("spawn")
    queue = ctx.Queue(maxsize=100)
    initialize_pool(None, queue)

    output_path = Path(tmp_path, "spatial.fgb")

    # Call the function
    worker(
        output_path=output_path,
        run_meta=run_meta,
        hazard=hazard_event_data,
        hazard_meta=hazard_meta_run,
        exposure=exposure_geom_data,
        exposure_meta=exposure_geom_meta_run,
        chunk=(1, 4),
    )

    # Drain the index records and finalize (as the parent model would)
    key, records = queue.get(timeout=10)
    profile = exposure_geom_data.profile
    fgb.finalize(
        key,
        f"{key}.body",
        "spatial",
        profile.geom_type,
        list(profile.fields) + list(exposure_geom_meta_run.new),
        list(profile.dtypes) + [fgb.CT_DOUBLE] * len(exposure_geom_meta_run.new),
        records,
        crs_wkt=profile.crs_wkt,
        crs_org=profile.crs_org,
        crs_code=profile.crs_code,
    )

    # Assert the output
    assert output_path.is_file()
    # Assert the content
    g = open_geom(output_path)
    assert g.profile.size == 4


def test_geom_worker_2d(
    run_meta: RunMeta,
    hazard_event_duration_data: NetcdfReader,
    hazard_meta_duration: HazardMeta,
    vulnerability_multi_meta: VulnerabilityMeta,
    exposure_geom_data: FlatGeobufReader,
    exposure_geom_data_run: ExposureGeomData,
):
    # Like geom_2d.toml
    exposure_meta = get_exposure_geom_meta(
        exposure=replace(exposure_geom_data_run, vulnerability="default_2d"),
        run_meta=run_meta,
        hazard_meta=hazard_meta_duration,
        vulnerability_meta=vulnerability_multi_meta,
    )
    method = flood.depth_duration_2d
    out_array = np.zeros(exposure_meta.new_length, dtype=np.float32)
    ft = _feature_by_id(exposure_geom_data, 1)

    # Call the function
    feature_worker(
        ft=ft,
        out_array=out_array,
        run_meta=run_meta,
        hazard=hazard_event_duration_data,
        hazard_meta=hazard_meta_duration,
        exposure_meta=exposure_meta,
        fn_hazard=method.fn_hazard,
        fn_impact=method.fn_impact,
    )

    # Assert the output, f(d, t) * E
    d, t, fact = _depth_duration(hazard_event_duration_data, ft, (0, 1))
    fn = vulnerability_multi_meta.datasets["default_2d"].fn["struct_1"]
    expected = fn(d, t) * 1000 * fact
    assert t > 0
    assert expected > 0
    np.testing.assert_almost_equal(out_array[0], d, decimal=4)
    np.testing.assert_almost_equal(out_array[1], t, decimal=4)
    np.testing.assert_almost_equal(out_array[2], expected, decimal=2)
    np.testing.assert_almost_equal(out_array[3], expected, decimal=2)


def test_geom_worker_risk_types(
    run_risk_meta: RunMeta,
    hazard_risk_data: NetcdfReader,
    hazard_risk_meta_run: HazardMeta,
    vulnerability_meta: VulnerabilityMeta,
    exposure_geom_types_data: FlatGeobufReader,
    exposure_geom_types_data_run: ExposureGeomData,
):
    exposure_meta = get_exposure_geom_meta(
        exposure=replace(exposure_geom_types_data_run, vulnerability="default"),
        run_meta=run_risk_meta,
        hazard_meta=hazard_risk_meta_run,
        vulnerability_meta=vulnerability_meta,
    )
    out_array = np.zeros(exposure_meta.new_length, dtype=np.float32)

    # Call the function
    feature_worker(
        ft=_feature_by_id(exposure_geom_types_data, 3),
        out_array=out_array,
        run_meta=run_risk_meta,
        hazard=hazard_risk_data,
        hazard_meta=hazard_risk_meta_run,
        exposure_meta=exposure_meta,
        fn_hazard=fn_hazard,
        fn_impact=fn_impact,
    )

    # Assert the output, one ead per impact type from its own totals
    eads = {}
    for t in ["damage", "affected"]:
        totals = out_array[exposure_meta.indices_total[t]]
        assert np.all(totals > 0)
        eads[t] = out_array[exposure_meta.indices_ead[t]]
        np.testing.assert_almost_equal(
            eads[t],
            fn_ead(hazard_risk_meta_run.density, totals),
            decimal=1,
        )
    np.testing.assert_almost_equal(eads["damage"], 1022.7, decimal=1)
    assert eads["damage"] != eads["affected"]
    np.testing.assert_almost_equal(eads["affected"], eads["damage"] / 10, decimal=1)


def test_geom_worker_uniform_hazard(
    tmp_path: Path,
    open_reader: Callable[..., NetcdfReader],
    hazard_event_path: Path,
    variables,
    run_meta: RunMeta,
    vulnerability_multi_meta: VulnerabilityMeta,
    exposure_geom_data: FlatGeobufReader,
    exposure_geom_data_run: ExposureGeomData,
):
    # Like geom_uniform.toml, a uniform duration layer
    hazard = open_reader(hazard_event_path)
    hazard.add_constant("duration", 3.0)
    hazard_meta = get_hazard_meta(
        hazard,
        variables.haz_event() + [HazardVariable(name="duration", type="duration")],
        risk=False,
        method_types=["water_depth", "duration"],
    )
    exposure_meta = get_exposure_geom_meta(
        exposure=replace(exposure_geom_data_run, vulnerability="default_2d"),
        run_meta=run_meta,
        hazard_meta=hazard_meta,
        vulnerability_meta=vulnerability_multi_meta,
    )
    assert exposure_meta.hazard_indices == [(0, 1)]

    # Setup the worker globals (lock + pipeline queue)
    ctx = get_context("spawn")
    queue = ctx.Queue(maxsize=100)
    initialize_pool(None, queue)
    output_path = Path(tmp_path, "spatial.fgb")

    # Call the function, the worker loads the hazard data (no window)
    worker(
        output_path=output_path,
        run_meta=run_meta,
        hazard=hazard,
        hazard_meta=hazard_meta,
        exposure=exposure_geom_data,
        exposure_meta=exposure_meta,
        chunk=(1, 4),
    )
    key, records = queue.get(timeout=10)
    _finalize(key, records, exposure_geom_data, exposure_meta.new)

    # Assert the constant duration band is fully loaded
    np.testing.assert_array_equal(hazard[1][:], 3.0)
    assert hazard[1][:].shape == hazard[0][:].shape

    # Assert the output, f(d, 3.0) * E
    ft = _feature_by_id(exposure_geom_data, 1)
    d, t, fact = _depth_duration(hazard, ft, (0, 1))
    fn = vulnerability_multi_meta.datasets["default_2d"].fn["struct_1"]
    expected = fn(d, 3.0) * 1000 * fact
    assert t == 3.0
    assert expected > 0
    g = open_geom(output_path)
    out = _feature_by_id(g, 1)
    np.testing.assert_almost_equal(out.get_field("duration_1"), 3.0)
    np.testing.assert_almost_equal(out.get_field("damage_structure_1"), expected, 2)


def test_geom_worker_duration_nodata(
    tmp_path: Path,
    open_reader: Callable[..., NetcdfReader],
    event_map_duration_path: Path,
    run_meta: RunMeta,
    hazard_meta_duration: HazardMeta,
    vulnerability_multi_meta: VulnerabilityMeta,
    exposure_geom_data: FlatGeobufReader,
    exposure_geom_data_run: ExposureGeomData,
):
    # Put the duration nodata value on a wet pixel of feature 1
    ft = _feature_by_id(exposure_geom_data, 1)
    p = Path(tmp_path, "event_map_duration.nc")
    shutil.copy2(event_map_duration_path, p)
    with nc4.Dataset(p, "a") as ds:
        lats = ds["lat"][:]
        lons = ds["lon"][:]
        gtf = (
            float(lons[0] - (lons[1] - lons[0]) / 2),
            float(lons[1] - lons[0]),
            0.0,
            float(lats[0] - (lats[1] - lats[0]) / 2),
            0.0,
            float(lats[1] - lats[0]),
        )
        mask, window = overlay.area_mask(
            geom=ft.geometry,
            gtf=gtf,
            shape=(len(lons), len(lats)),
        )
        depth = np.asarray(ds["depth"][window])
        rows, cols = np.nonzero((mask == 1) & (depth > 0))
        assert len(rows) > 0
        duration = np.asarray(ds["duration"][window])
        duration[rows[0], cols[0]] = ds["duration"]._FillValue
        ds["duration"][window] = duration
    hazard = open_reader(p)
    exposure_meta = get_exposure_geom_meta(
        exposure=replace(exposure_geom_data_run, vulnerability="default_2d"),
        run_meta=run_meta,
        hazard_meta=hazard_meta_duration,
        vulnerability_meta=vulnerability_multi_meta,
    )

    # Setup the worker globals (lock + pipeline queue)
    ctx = get_context("spawn")
    queue = ctx.Queue(maxsize=100)
    initialize_pool(None, queue)
    output_path = Path(tmp_path, "spatial.fgb")

    # Call the function
    worker(
        output_path=output_path,
        run_meta=run_meta,
        hazard=hazard,
        hazard_meta=hazard_meta_duration,
        exposure=exposure_geom_data,
        exposure_meta=exposure_meta,
        chunk=(1, 4),
    )
    key, records = queue.get(timeout=10)
    _finalize(key, records, exposure_geom_data, exposure_meta.new)

    # Assert the nodata is masked: nan duration, impact zero (nan rule)
    g = open_geom(output_path)
    out = _feature_by_id(g, 1)
    assert math.isnan(out.get_field("duration_1"))
    assert out.get_field("damage_structure_1") == 0
    assert out.get_field("total_damage_1") == 0
    # Other features are unaffected
    out = _feature_by_id(g, 3)
    assert out.get_field("duration_1") > 0
    assert out.get_field("damage_structure_1") > 0


def test_geom_worker_int_duration_nodata(
    tmp_path: Path,
    open_reader: Callable[..., NetcdfReader],
    event_map_duration_path: Path,
    int16_nc_copy: Callable[[Path, str], Path],
    run_meta: RunMeta,
    hazard_meta_duration: HazardMeta,
    vulnerability_multi_meta: VulnerabilityMeta,
    exposure_geom_data: FlatGeobufReader,
    exposure_geom_data_run: ExposureGeomData,
):
    # Integer (int16) duration band with nodata on a wet pixel of feature 1
    ft = _feature_by_id(exposure_geom_data, 1)
    p = int16_nc_copy(event_map_duration_path, "duration")
    hazard = open_reader(p)
    mask, window = overlay.area_mask(
        geom=ft.geometry,
        gtf=hazard.profile.transform,
        shape=hazard.profile.shape_xy,
    )
    hazard.close()
    with nc4.Dataset(p, "a") as ds:
        depth = np.asarray(ds["depth"][window])
        rows, cols = np.nonzero((mask == 1) & (depth > 0))
        assert len(rows) > 0
        duration = np.asarray(ds["duration"][window])
        duration[rows[0], cols[0]] = -9999
        ds["duration"][window] = duration
    hazard = open_reader(p)
    hazard.load()
    assert np.issubdtype(hazard[1].data.dtype, np.integer)
    exposure_meta = get_exposure_geom_meta(
        exposure=replace(exposure_geom_data_run, vulnerability="default_2d"),
        run_meta=run_meta,
        hazard_meta=hazard_meta_duration,
        vulnerability_meta=vulnerability_multi_meta,
    )

    # Setup the worker globals (lock + pipeline queue)
    ctx = get_context("spawn")
    queue = ctx.Queue(maxsize=100)
    initialize_pool(None, queue)
    output_path = Path(tmp_path, "spatial.fgb")

    # Call the function
    worker(
        output_path=output_path,
        run_meta=run_meta,
        hazard=hazard,
        hazard_meta=hazard_meta_duration,
        exposure=exposure_geom_data,
        exposure_meta=exposure_meta,
        chunk=(1, 4),
    )
    key, records = queue.get(timeout=10)
    _finalize(key, records, exposure_geom_data, exposure_meta.new)

    # Assert the -9999 is not used: nan duration, impact zero (nan rule)
    g = open_geom(output_path)
    out = _feature_by_id(g, 1)
    assert math.isnan(out.get_field("duration_1"))
    assert out.get_field("damage_structure_1") == 0
    # Other features use the integer durations as is
    out = _feature_by_id(g, 3)
    assert out.get_field("duration_1") == 3
    assert out.get_field("damage_structure_1") > 0


def test_worker_depth_values(
    tmp_path: Path,
    run_meta: RunMeta,
    hazard_event_data: NetcdfReader,
    hazard_meta_run: HazardMeta,
    exposure_geom_data: FlatGeobufReader,
    exposure_geom_meta_run: ExposureGeomMeta,
):
    # Depth only run (like geom_event), the numbers are unchanged
    ctx = get_context("spawn")
    queue = ctx.Queue(maxsize=100)
    initialize_pool(None, queue)
    output_path = Path(tmp_path, "spatial.fgb")
    worker(
        output_path=output_path,
        run_meta=run_meta,
        hazard=hazard_event_data,
        hazard_meta=hazard_meta_run,
        exposure=exposure_geom_data,
        exposure_meta=exposure_geom_meta_run,
        chunk=(1, 4),
    )
    key, records = queue.get(timeout=10)
    _finalize(key, records, exposure_geom_data, exposure_geom_meta_run.new)

    # Assert the output
    out = _feature_by_id(open_geom(output_path), 1)
    np.testing.assert_almost_equal(out.get_field("depth_1"), 3.4, decimal=2)
    np.testing.assert_almost_equal(out.get_field("total_damage_1"), 760, decimal=0)
