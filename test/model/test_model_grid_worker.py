import shutil
from dataclasses import replace
from pathlib import Path
from typing import Callable

import netCDF4 as nc4
import numpy as np

from fiat.driver import NetcdfReader
from fiat.driver.geotiff import GeotiffReader, create_geotiff_handle
from fiat.method import flood
from fiat.model.grid_worker import (
    array_worker,
    initialize_pool,
    worker,
)
from fiat.model.meta import (
    ExposureGridMeta,
    HazardMeta,
    RunMeta,
    VulnerabilityMeta,
    get_exposure_grid_meta,
)
from fiat.util import NODATA_VALUE


def _fns(exposure_meta: ExposureGridMeta) -> dict:
    mods = {
        "flood.depth": flood.depth,
        "flood.depth_duration": flood.depth_duration,
        "flood.depth_duration_2d": flood.depth_duration_2d,
    }
    return {item.method: mods[item.method].fn_impact for item in exposure_meta.units}


def _nodata_nan(var) -> np.ndarray:
    a = np.array(var.data, dtype=np.float64)
    if var.nodata is not None:
        a[a == var.nodata] = np.nan
    return a


def test_array_worker(
    run_meta: RunMeta,
    hazard_event_data: NetcdfReader,
    hazard_meta_run: HazardMeta,
    exposure_grid_data: NetcdfReader,
    exposure_grid_meta_run: ExposureGridMeta,
):
    # Create the out_array
    out_array = np.zeros((exposure_grid_meta_run.nb, 10, 10)) * np.nan
    # Call the function
    array_worker(
        out_array=out_array,
        run_meta=run_meta,
        hazard=hazard_event_data,
        hazard_meta=hazard_meta_run,
        exposure=exposure_grid_data,
        exposure_meta=exposure_grid_meta_run,
        fns=_fns(exposure_grid_meta_run),
    )

    # Assert the output
    assert out_array.shape == (exposure_grid_meta_run.nb, 10, 10)
    np.testing.assert_almost_equal(np.nanmean(out_array[0]), 941, decimal=0)
    np.testing.assert_almost_equal(np.nanmax(out_array[0]), 1897, decimal=0)
    np.testing.assert_almost_equal(np.nanmean(out_array[1]), 2036, decimal=0)
    np.testing.assert_almost_equal(np.nanmax(out_array[1]), 4410, decimal=0)
    np.testing.assert_almost_equal(np.nanmean(out_array[2]), 2487, decimal=0)
    np.testing.assert_almost_equal(np.nanmax(out_array[2]), 4648, decimal=0)


def test_array_worker_cat(
    run_meta: RunMeta,
    hazard_event_data: NetcdfReader,
    hazard_meta_run: HazardMeta,
    exposure_grid_cat_data: NetcdfReader,
    exposure_grid_cat_meta_run: ExposureGridMeta,
):
    # Create the out_array
    out_array = np.zeros((exposure_grid_cat_meta_run.nb, 10, 10)) * np.nan
    # Call the function
    array_worker(
        out_array=out_array,
        run_meta=run_meta,
        hazard=hazard_event_data,
        hazard_meta=hazard_meta_run,
        exposure=exposure_grid_cat_data,
        exposure_meta=exposure_grid_cat_meta_run,
        fns=_fns(exposure_grid_cat_meta_run),
    )

    # Assert the output
    assert out_array.shape == (exposure_grid_cat_meta_run.nb, 10, 10)
    # Cell (8, 8) has a zero damage fraction, which is set to nan
    assert np.isnan(out_array[0, 8, 8])
    assert np.isfinite(out_array[0]).sum() == 5

    # Assert the propagation per category (1: value 5000, 2: value 3000)
    np.testing.assert_almost_equal(out_array[0, 0, 1], 3800, decimal=0)
    np.testing.assert_almost_equal(out_array[0, 3, 9], 560, decimal=0)
    np.testing.assert_almost_equal(out_array[0, 1, 5], 2382, decimal=0)
    np.testing.assert_almost_equal(out_array[0, 5, 6], 906, decimal=0)
    np.testing.assert_almost_equal(out_array[0, 9, 2], 906, decimal=0)

    # The second category value variable (1: value 2500, 2: value 1500)
    np.testing.assert_allclose(out_array[1], out_array[0] / 2, rtol=1e-6)

    # Assert the total, the sum of both category value variables
    np.testing.assert_allclose(out_array[2], out_array[0] * 1.5, rtol=1e-6)


def test_array_worker_risk(
    run_risk_meta: RunMeta,
    hazard_risk_data: NetcdfReader,
    hazard_risk_meta_run: HazardMeta,
    exposure_grid_data: NetcdfReader,
    exposure_grid_risk_meta_run: ExposureGridMeta,
):
    # Create the out_array
    out_array = np.zeros((exposure_grid_risk_meta_run.nb, 10, 10)) * np.nan
    # Call the function
    array_worker(
        out_array=out_array,
        run_meta=run_risk_meta,
        hazard=hazard_risk_data,
        hazard_meta=hazard_risk_meta_run,
        exposure=exposure_grid_data,
        exposure_meta=exposure_grid_risk_meta_run,
        fns=_fns(exposure_grid_risk_meta_run),
    )

    # Assert the output
    assert out_array.shape == (exposure_grid_risk_meta_run.nb, 10, 10)
    np.testing.assert_almost_equal(np.nanmean(out_array[0]), 1685, decimal=0)
    np.testing.assert_almost_equal(np.nanmax(out_array[0]), 2786, decimal=0)
    np.testing.assert_almost_equal(np.nanmean(out_array[3]), 2114, decimal=0)
    np.testing.assert_almost_equal(np.nanmax(out_array[3]), 3331, decimal=0)
    np.testing.assert_almost_equal(np.nanmean(out_array[7]), 3837, decimal=0)
    np.testing.assert_almost_equal(np.nanmax(out_array[7]), 6720, decimal=0)
    np.testing.assert_almost_equal(np.nanmean(out_array[12]), 2289, decimal=0)
    np.testing.assert_almost_equal(np.nanmax(out_array[12]), 3453, decimal=0)

    # Assert the propagation of one cell
    np.testing.assert_almost_equal(out_array[0, 9, 2], 2107, decimal=0)
    np.testing.assert_almost_equal(out_array[4, 9, 2], 3707, decimal=0)
    np.testing.assert_almost_equal(out_array[8, 9, 2], 5814, decimal=0)
    np.testing.assert_almost_equal(out_array[12, 9, 2], 3453, decimal=0)


def test_array_worker_combined(
    variables,
    run_meta: RunMeta,
    hazard_event_duration_data: NetcdfReader,
    hazard_meta_duration: HazardMeta,
    vulnerability_multi_meta: VulnerabilityMeta,
    exposure_grid_combined_data: NetcdfReader,
):
    # Get the meta
    meta = get_exposure_grid_meta(
        exposure_grid_combined_data,
        variables.exp_grid_combined(),
        run_meta=run_meta,
        hazard_meta=hazard_meta_duration,
        vulnerability_meta=vulnerability_multi_meta,
    )
    d = _nodata_nan(hazard_event_duration_data[0])
    t = _nodata_nan(hazard_event_duration_data[1])
    e1 = _nodata_nan(exposure_grid_combined_data[0])
    e2 = _nodata_nan(exposure_grid_combined_data[1])

    # Call the function
    out_array = np.full((meta.nb, 10, 10), np.nan)
    array_worker(
        out_array=out_array,
        run_meta=run_meta,
        hazard=hazard_event_duration_data,
        hazard_meta=hazard_meta_duration,
        exposure=exposure_grid_combined_data,
        exposure_meta=meta,
        fns=_fns(meta),
    )

    # Assert the output
    ds = vulnerability_multi_meta.datasets
    np.testing.assert_allclose(
        out_array[0], ds["default"].fn["struct_1"](d) * e1, rtol=1e-6
    )
    expected = ds["direct"].fn["struct_2"](d) * ds["indirect"].fn["struct_2"](t) * e2
    np.testing.assert_allclose(out_array[1], expected, rtol=1e-6)
    assert np.nanmax(out_array[1]) > 0
    total = np.nansum([out_array[0], out_array[1]], axis=0)
    total[np.isnan(out_array[0]) & np.isnan(out_array[1])] = np.nan
    np.testing.assert_allclose(out_array[2], total, rtol=1e-6)


def test_array_worker_2d(
    variables,
    run_meta: RunMeta,
    hazard_event_duration_data: NetcdfReader,
    hazard_meta_duration: HazardMeta,
    vulnerability_multi_meta: VulnerabilityMeta,
    exposure_grid_data: NetcdfReader,
):
    # Get the meta
    meta = get_exposure_grid_meta(
        exposure_grid_data,
        variables.exp_grid(default="default_2d"),
        run_meta=run_meta,
        hazard_meta=hazard_meta_duration,
        vulnerability_meta=vulnerability_multi_meta,
    )
    d = _nodata_nan(hazard_event_duration_data[0])
    t = _nodata_nan(hazard_event_duration_data[1])
    e2 = _nodata_nan(exposure_grid_data[1])

    # Call the function
    out_array = np.full((meta.nb, 10, 10), np.nan)
    array_worker(
        out_array=out_array,
        run_meta=run_meta,
        hazard=hazard_event_duration_data,
        hazard_meta=hazard_meta_duration,
        exposure=exposure_grid_data,
        exposure_meta=meta,
        fns=_fns(meta),
    )

    # Assert the output
    fn = vulnerability_multi_meta.datasets["default_2d"].fn["struct_2"]
    np.testing.assert_allclose(out_array[1], fn(d, t) * e2, rtol=1e-6)
    assert np.nanmax(out_array[1]) > 0


def test_array_worker_combined_nan(
    variables,
    tmp_path: Path,
    open_reader: Callable[..., NetcdfReader],
    event_map_duration_path: Path,
    run_meta: RunMeta,
    hazard_meta_duration: HazardMeta,
    vulnerability_multi_meta: VulnerabilityMeta,
    exposure_grid_combined_data: NetcdfReader,
):
    # Copy of the hazard with a nodata duration in cell (0, 0)
    p = Path(tmp_path, "event_map_duration.nc")
    shutil.copy2(event_map_duration_path, p)
    with nc4.Dataset(p, "a") as ds:
        ds["duration"][0, 0] = ds["duration"]._FillValue
    hazard = open_reader(p)
    hazard.load()

    # Only the combined unit
    meta = get_exposure_grid_meta(
        exposure_grid_combined_data,
        variables.exp_grid_combined(),
        run_meta=run_meta,
        hazard_meta=hazard_meta_duration,
        vulnerability_meta=vulnerability_multi_meta,
    )
    meta = ExposureGridMeta(
        index_ead=None,
        indices_total=[1],
        nb=2,
        new=["exposure2_1", "total_1"],
        totals=[[0]],
        units=[replace(meta.units[1], out_indices=[0])],
    )

    # Call the function
    out_array = np.full((meta.nb, 10, 10), np.nan)
    array_worker(
        out_array=out_array,
        run_meta=run_meta,
        hazard=hazard,
        hazard_meta=hazard_meta_duration,
        exposure=exposure_grid_combined_data,
        exposure_meta=meta,
        fns=_fns(meta),
    )

    # Assert the output
    assert np.isnan(out_array[0, 0, 0])
    assert np.isnan(out_array[1, 0, 0])
    assert np.isfinite(out_array[0, 0, 1])
    assert np.isfinite(out_array[1, 0, 1])


def test_array_worker_int_duration_nodata(
    variables,
    open_reader: Callable[..., NetcdfReader],
    event_map_duration_path: Path,
    int16_nc_copy: Callable[[Path, str], Path],
    run_meta: RunMeta,
    hazard_event_duration_data: NetcdfReader,
    hazard_meta_duration: HazardMeta,
    vulnerability_multi_meta: VulnerabilityMeta,
    exposure_grid_combined_data: NetcdfReader,
):
    # Integer (int16) duration band with a nodata duration in cell (0, 0)
    p = int16_nc_copy(event_map_duration_path, "duration")
    with nc4.Dataset(p, "a") as ds:
        ds["duration"][0, 0] = -9999
    hazard = open_reader(p)
    hazard.load()
    assert np.issubdtype(hazard[1].data.dtype, np.integer)

    meta = get_exposure_grid_meta(
        exposure_grid_combined_data,
        variables.exp_grid_combined(),
        run_meta=run_meta,
        hazard_meta=hazard_meta_duration,
        vulnerability_meta=vulnerability_multi_meta,
    )
    d = _nodata_nan(hazard_event_duration_data[0])
    t = _nodata_nan(hazard_event_duration_data[1])
    e2 = _nodata_nan(exposure_grid_combined_data[1])

    # Call the function
    out_array = np.full((meta.nb, 10, 10), np.nan)
    array_worker(
        out_array=out_array,
        run_meta=run_meta,
        hazard=hazard,
        hazard_meta=hazard_meta_duration,
        exposure=exposure_grid_combined_data,
        exposure_meta=meta,
        fns=_fns(meta),
    )

    # Assert the output, nodata cell is nan for the duration unit
    ds = vulnerability_multi_meta.datasets
    expected = ds["direct"].fn["struct_2"](d) * ds["indirect"].fn["struct_2"](t) * e2
    expected[0, 0] = np.nan
    np.testing.assert_allclose(out_array[1], expected, rtol=1e-6)
    assert np.isnan(out_array[1, 0, 0])
    assert np.nanmax(out_array[1]) > 0
    total = np.nansum([out_array[0], out_array[1]], axis=0)
    total[np.isnan(out_array[0]) & np.isnan(out_array[1])] = np.nan
    np.testing.assert_allclose(out_array[2], total, rtol=1e-6)


def test_array_worker_cat_uniform(
    variables,
    run_meta: RunMeta,
    hazard_event_duration_data: NetcdfReader,
    hazard_meta_duration: HazardMeta,
    vulnerability_cat_meta: VulnerabilityMeta,
    exposure_grid_cat_uniform_data: NetcdfReader,
):
    # Get the meta
    meta = get_exposure_grid_meta(
        exposure_grid_cat_uniform_data,
        variables.exp_cat_uniform(),
        run_meta=run_meta,
        hazard_meta=hazard_meta_duration,
        vulnerability_meta=vulnerability_cat_meta,
    )
    d = _nodata_nan(hazard_event_duration_data[0])

    # Call the function
    out_array = np.full((meta.nb, 10, 10), np.nan)
    array_worker(
        out_array=out_array,
        run_meta=run_meta,
        hazard=hazard_event_duration_data,
        hazard_meta=hazard_meta_duration,
        exposure=exposure_grid_cat_uniform_data,
        exposure_meta=meta,
        fns=_fns(meta),
    )

    # Assert the output, category 1 (value 5000) everywhere
    expected = vulnerability_cat_meta.datasets["default"].fn[1](d) * 5000
    expected[expected == 0] = np.nan
    np.testing.assert_allclose(out_array[1], expected, rtol=1e-6)
    assert np.isfinite(out_array[1]).sum() > 5


def test_worker(
    tmp_path: Path,
    run_meta: RunMeta,
    hazard_event_data: NetcdfReader,
    hazard_meta_run: HazardMeta,
    exposure_grid_data: NetcdfReader,
    exposure_grid_meta_run: ExposureGridMeta,
):
    from multiprocessing import get_context

    # Create a GeoTIFF output handle and open it for parallel tile writes.
    out = Path(tmp_path, "out.tif")
    handle = create_geotiff_handle(
        path=out,
        variables=exposure_grid_meta_run.new,
        ds_like=exposure_grid_data,
        crs=exposure_grid_data.profile.crs,
        tile=(10, 10),
    )
    lock = handle.start_parallel(get_context("spawn"))
    initialize_pool(handle.sink_descriptor(), lock)

    # Call the function; it writes the tile directly and returns its records.
    records = worker(
        run_meta=run_meta,
        hazard=hazard_event_data,
        hazard_meta=hazard_meta_run,
        exposure=exposure_grid_data,
        exposure_meta=exposure_grid_meta_run,
        window=(slice(0, 10), slice(0, 10)),
    )
    assert records

    handle.collect_records([records])
    handle.close()

    # Read the output back and mask nodata for comparison with array_worker.
    reader = GeotiffReader(str(out))

    def band(i):
        a = reader[i].load().astype("float64")
        a[a == NODATA_VALUE] = np.nan
        return a

    np.testing.assert_almost_equal(np.nanmean(band(0)), 941, decimal=0)
    np.testing.assert_almost_equal(np.nanmax(band(0)), 1897, decimal=0)
    np.testing.assert_almost_equal(np.nanmean(band(1)), 2036, decimal=0)
    np.testing.assert_almost_equal(np.nanmax(band(1)), 4410, decimal=0)
    np.testing.assert_almost_equal(np.nanmean(band(2)), 2487, decimal=0)
    np.testing.assert_almost_equal(np.nanmax(band(2)), 4648, decimal=0)
    reader.close()
