from multiprocessing.shared_memory import SharedMemory

import numpy as np

from fiat.fio import GridIO
from fiat.method import flood
from fiat.model.grid_worker import (
    array_worker,
    initialize_pool,
    process_hazard,
    worker,
)
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
    vulnerability_meta_run: VulnerabilityMeta,
    exposure_grid_data: GridIO,
    exposure_grid_meta_run: ExposureGridMeta,
):
    # Create the out_array
    out_array = np.zeros((3, 10, 10)) * np.nan
    # Call the function
    array_worker(
        out_array=out_array,
        hazard=hazard_event_data,
        hazard_meta=hazard_meta_run,
        vulnerability_meta=vulnerability_meta_run,
        exposure=exposure_grid_data,
        exposure_meta=exposure_grid_meta_run,
        fn_impact=flood.fn_impact,
        window=(0, 0, 10, 10),
    )

    # Assert the output
    assert out_array.shape == (3, 10, 10)
    np.testing.assert_almost_equal(np.nanmean(out_array[0]), 941, decimal=0)
    np.testing.assert_almost_equal(np.nanmax(out_array[0]), 1897, decimal=0)
    np.testing.assert_almost_equal(np.nanmean(out_array[1]), 2036, decimal=0)
    np.testing.assert_almost_equal(np.nanmax(out_array[1]), 4410, decimal=0)
    np.testing.assert_almost_equal(np.nanmean(out_array[2]), 2487, decimal=0)
    np.testing.assert_almost_equal(np.nanmax(out_array[2]), 4648, decimal=0)


class DummyQueue:
    def put_nowait(self, item): ...


class DummyPipeline:
    def recv(self): ...


def test_worker(
    hazard_event_data: GridIO,
    hazard_meta_run: HazardMeta,
    vulnerability_meta_run: VulnerabilityMeta,
    exposure_grid_data: GridIO,
    exposure_grid_meta_run: ExposureGridMeta,
):
    # Create a block of shared memory to work with
    shm = SharedMemory(name="test-block", create=True, size=300 * 4)
    arr = np.ndarray(shape=(3, 10, 10), dtype=np.float32, buffer=shm.buf)
    arr[:] = np.nan
    initialize_pool(q=DummyQueue(), p={"test-block": DummyPipeline()})

    # Call the function
    worker(
        mem_id="test-block",
        hazard=hazard_event_data,
        hazard_meta=hazard_meta_run,
        vulnerability_meta=vulnerability_meta_run,
        exposure=exposure_grid_data,
        exposure_meta=exposure_grid_meta_run,
        chunk=(0, 0, 10, 10),
        window=(10, 10),
    )

    # Assert the output, same as the array worker
    np.testing.assert_almost_equal(np.nanmean(arr[0]), 941, decimal=0)
    np.testing.assert_almost_equal(np.nanmax(arr[0]), 1897, decimal=0)
    np.testing.assert_almost_equal(np.nanmean(arr[1]), 2036, decimal=0)
    np.testing.assert_almost_equal(np.nanmax(arr[1]), 4410, decimal=0)
    np.testing.assert_almost_equal(np.nanmean(arr[2]), 2487, decimal=0)
    np.testing.assert_almost_equal(np.nanmax(arr[2]), 4648, decimal=0)

    # Close down
    arr = None
    shm.close()
    shm.unlink()
