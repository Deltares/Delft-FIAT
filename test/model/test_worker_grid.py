from pathlib import Path

import numpy as np

from fiat.fio import GridIO, open_grid
from fiat.method import flood
from fiat.model.util import vectorize_function
from fiat.model.worker_grid import array_worker, process_hazard, worker
from fiat.struct import Table
from fiat.struct.container import ExposureGridMeta, HazardMeta, VulnerabilityMeta


def test_process_hazard(
    hazard_event_data: GridIO,
    vulnerability_meta_run: VulnerabilityMeta,
):
    # Call the function
    a = process_hazard(
        band=hazard_event_data[0],
        window=(0, 0, 10, 10),
        vulnerability_meta=vulnerability_meta_run,
    )

    # Assert the output
    assert a.shape == (10, 10)
    np.testing.assert_almost_equal(a.mean(), 1.8)
    np.testing.assert_almost_equal(a[0, 0], 3.6)
    np.testing.assert_almost_equal(a[9, 9], 0.0)
    assert a.max() <= vulnerability_meta_run.max


def test_array_worker(
    hazard_event_data: GridIO,
    hazard_meta_run: HazardMeta,
    vulnerability_data_run: Table,
    vulnerability_meta_run: VulnerabilityMeta,
    exposure_grid_data: GridIO,
    exposure_grid_meta_run: ExposureGridMeta,
):
    # Set up the vectorized function
    fn_impact = vectorize_function(
        fn=flood.fn_impact_single, skip=hazard_meta_run.type_length + 1
    )

    # Call the function
    out_array = array_worker(
        hazard=hazard_event_data,
        hazard_meta=hazard_meta_run,
        vulnerability=vulnerability_data_run,
        vulnerability_meta=vulnerability_meta_run,
        exposure=exposure_grid_data,
        exposure_meta=exposure_grid_meta_run,
        fn_impact=fn_impact,
        window=(0, 0, 10, 10),
    )

    # Assert the output
    assert out_array.shape == (3, 10, 10)
    np.testing.assert_almost_equal(np.nanmean(out_array[0]), 941, decimal=0)
    np.testing.assert_almost_equal(np.nanmax(out_array[0]), 1897, decimal=0)
    np.testing.assert_almost_equal(np.nanmean(out_array[1]), 1436, decimal=0)
    np.testing.assert_almost_equal(np.nanmax(out_array[1]), 3010, decimal=0)
    np.testing.assert_almost_equal(np.nanmean(out_array[2]), 1962, decimal=0)
    np.testing.assert_almost_equal(np.nanmax(out_array[2]), 4028, decimal=0)


def test_worker(
    tmp_path: Path,
    hazard_event_data: GridIO,
    hazard_meta_run: HazardMeta,
    vulnerability_data_run: Table,
    vulnerability_meta_run: VulnerabilityMeta,
    exposure_grid_data: GridIO,
    exposure_grid_meta_run: ExposureGridMeta,
):
    # Call the function
    worker(
        output_dir=tmp_path,
        hazard=hazard_event_data,
        hazard_meta=hazard_meta_run,
        vulnerability=vulnerability_data_run,
        vulnerability_meta=vulnerability_meta_run,
        exposure=exposure_grid_data,
        exposure_meta=exposure_grid_meta_run,
        chunk=(0, 0, 10, 10),
    )

    # Assert the output
    p = Path(tmp_path, "spatial.nc")
    assert p.is_file()
    # Assert the content
    g = open_grid(p, var_as_band=True)
    assert g.size == 3
