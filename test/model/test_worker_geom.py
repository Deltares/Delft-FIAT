from pathlib import Path

import numpy as np

from fiat.fio import GeomIO, GridIO, open_geom
from fiat.method.flood import fn_hazard, fn_impact
from fiat.model.worker_geom import feature_worker, worker
from fiat.struct import Table
from fiat.struct.container import ExposureMeta, HazardMeta, VulnerabilityMeta


def test_feature_worker(
    hazard_event_data: GridIO,
    hazard_meta_run: HazardMeta,
    vulnerability_data_run: Table,
    vulnerability_meta_run: VulnerabilityMeta,
    exposure_geom_dataset: GeomIO,
    exposure_meta_run: ExposureMeta,
):
    # Call the function
    a = feature_worker(
        ft=exposure_geom_dataset.layer[0],
        hazard=hazard_event_data,
        hazard_meta=hazard_meta_run,
        vulnerability=vulnerability_data_run,
        vulnerability_meta=vulnerability_meta_run,
        exposure_meta=exposure_meta_run,
        fn_hazard=fn_hazard,
        fn_impact=fn_impact,
    )

    # Assert the output
    np.testing.assert_array_almost_equal(a, [3.4, 760, 760], decimal=2)


def test_feature_worker_risk(
    hazard_risk_data: GridIO,
    hazard_risk_meta_run: HazardMeta,
    vulnerability_data_run: Table,
    vulnerability_meta_run: VulnerabilityMeta,
    exposure_geom_dataset: GeomIO,
    exposure_meta_run: ExposureMeta,
):
    # Call the function
    a = feature_worker(
        ft=exposure_geom_dataset.layer[2],
        hazard=hazard_risk_data,
        hazard_meta=hazard_risk_meta_run,
        vulnerability=vulnerability_data_run,
        vulnerability_meta=vulnerability_meta_run,
        exposure_meta=exposure_meta_run,
        fn_hazard=fn_hazard,
        fn_impact=fn_impact,
    )

    # Assert the output
    assert len(a) == (exposure_meta_run.type_length * hazard_risk_data.size + 1)
    np.testing.assert_almost_equal(a[0], 2.61, decimal=2)
    np.testing.assert_almost_equal(a[2], 1789.2)
    np.testing.assert_almost_equal(a[6], 3.31, decimal=2)
    np.testing.assert_almost_equal(a[10], 2280)
    np.testing.assert_almost_equal(a[-1], 1085.68)


def test_worker(
    tmp_path: Path,
    hazard_event_data: GridIO,
    hazard_meta_run: HazardMeta,
    vulnerability_data_run: Table,
    vulnerability_meta_run: VulnerabilityMeta,
    exposure_geom_dataset: GeomIO,
    exposure_meta_run: ExposureMeta,
):
    # Call the function
    worker(
        output_dir=tmp_path,
        hazard=hazard_event_data,
        hazard_meta=hazard_meta_run,
        vulnerability=vulnerability_data_run,
        vulnerability_meta=vulnerability_meta_run,
        exposure=exposure_geom_dataset,
        exposure_meta=exposure_meta_run,
        chunk=(1, 4),
        queue=None,
        lock=None,
    )

    # Assert the output
    p = Path(tmp_path, "spatial.gpkg")
    assert p.is_file()
    # Assert the content
    g = open_geom(p)
    assert g.layer.size == 4
