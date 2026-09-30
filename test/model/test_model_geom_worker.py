from multiprocessing import get_context
from pathlib import Path

import numpy as np

from fiat.container import (
    ExposureGeomMeta,
    HazardMeta,
    RunMeta,
    VulnerabilityMeta,
)
from fiat.driver import FlatGeobufDriver, NetcdfDriver, fgb
from fiat.method.flood.depth import fn_hazard, fn_impact
from fiat.model.geom_worker import feature_worker, initialize_pool, worker
from fiat.open import open_geom


def _feature_by_id(layer, object_id):
    """Return the feature with a given object_id (order-independent)."""
    for ft in layer:
        if ft.get_field("object_id") == object_id:
            return ft
    raise AssertionError(f"No feature with object_id={object_id}")


def test_feature_worker(
    run_meta: RunMeta,
    hazard_event_data: NetcdfDriver,
    hazard_meta_run: HazardMeta,
    vulnerability_meta_run: VulnerabilityMeta,
    exposure_geom_data: FlatGeobufDriver,
    exposure_geom_meta_run: ExposureGeomMeta,
):
    # Create the array
    out_array = np.zeros(exposure_geom_meta_run.new_length, dtype=np.float32)

    # Call the function
    feature_worker(
        ft=_feature_by_id(exposure_geom_data.layer, 1),
        out_array=out_array,
        run_meta=run_meta,
        hazard=hazard_event_data,
        hazard_meta=hazard_meta_run,
        vulnerability_meta=vulnerability_meta_run,
        exposure_meta=exposure_geom_meta_run,
        fn_hazard=fn_hazard,
        fn_impact=fn_impact,
    )

    # Assert the output
    np.testing.assert_array_almost_equal(out_array, [3.4, 760, 760], decimal=2)


def test_feature_worker_risk(
    run_risk_meta: RunMeta,
    hazard_risk_data: NetcdfDriver,
    hazard_risk_meta_run: HazardMeta,
    vulnerability_meta_run: VulnerabilityMeta,
    exposure_geom_data: FlatGeobufDriver,
    exposure_geom_risk_meta_run: ExposureGeomMeta,
):
    # Create the array
    out_array = np.zeros(exposure_geom_risk_meta_run.new_length, dtype=np.float32)

    # Call the function
    feature_worker(
        ft=_feature_by_id(exposure_geom_data.layer, 3),
        out_array=out_array,
        run_meta=run_risk_meta,
        hazard=hazard_risk_data,
        hazard_meta=hazard_risk_meta_run,
        vulnerability_meta=vulnerability_meta_run,
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


def test_worker(
    tmp_path: Path,
    run_meta: RunMeta,
    hazard_event_data: NetcdfDriver,
    hazard_meta_run: HazardMeta,
    vulnerability_meta_run: VulnerabilityMeta,
    exposure_geom_data: FlatGeobufDriver,
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
        vulnerability_meta=vulnerability_meta_run,
        exposure=exposure_geom_data,
        exposure_meta=exposure_geom_meta_run,
        chunk=(1, 4),
    )

    # Drain the index records and finalize (as the parent model would)
    key, records = queue.get(timeout=10)
    layer = exposure_geom_data.layer
    reader = layer._reader
    fgb.finalize(
        key,
        f"{key}.body",
        "spatial",
        layer.geom_type,
        list(layer.fields) + list(exposure_geom_meta_run.new),
        list(layer.dtypes) + [fgb.CT_DOUBLE] * len(exposure_geom_meta_run.new),
        records,
        crs_wkt=reader.crs_wkt,
        crs_org=reader.crs_org,
        crs_code=reader.crs_code,
    )

    # Assert the output
    assert output_path.is_file()
    # Assert the content
    g = open_geom(output_path)
    assert g.layer.size == 4
