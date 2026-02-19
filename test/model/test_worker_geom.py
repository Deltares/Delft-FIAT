from pathlib import Path

import numpy as np

from fiat.fio import GeomIO, GridIO, open_geom
from fiat.method.flood import fn_hazard, fn_impact
from fiat.model.worker_geom import feature_worker, worker
from fiat.struct.container import ExposureGeomMeta, HazardMeta, VulnerabilityMeta


def test_feature_worker(
    hazard_event_data: GridIO,
    hazard_meta_run: HazardMeta,
    vulnerability_meta_run: VulnerabilityMeta,
    exposure_geom_data: GeomIO,
    exposure_geom_meta_run: ExposureGeomMeta,
):
    # Call the function
    out_array = feature_worker(
        ft=exposure_geom_data.layer[0],
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
    hazard_risk_data: GridIO,
    hazard_risk_meta_run: HazardMeta,
    vulnerability_meta_run: VulnerabilityMeta,
    exposure_geom_data: GeomIO,
    exposure_geom_risk_meta_run: ExposureGeomMeta,
):
    # Call the function
    out_array = feature_worker(
        ft=exposure_geom_data.layer[2],
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
    np.testing.assert_almost_equal(out_array[-1], 1085.8, decimal=1)


def test_worker(
    tmp_path: Path,
    hazard_event_data: GridIO,
    hazard_meta_run: HazardMeta,
    vulnerability_meta_run: VulnerabilityMeta,
    exposure_geom_data: GeomIO,
    exposure_geom_meta_run: ExposureGeomMeta,
):
    # Call the function
    worker(
        output_dir=tmp_path,
        hazard=hazard_event_data,
        hazard_meta=hazard_meta_run,
        vulnerability_meta=vulnerability_meta_run,
        exposure=exposure_geom_data,
        exposure_meta=exposure_geom_meta_run,
        chunk=(1, 4),
    )

    # Assert the output
    p = Path(tmp_path, "spatial.gpkg")
    assert p.is_file()
    # Assert the content
    g = open_geom(p)
    assert g.layer.size == 4
