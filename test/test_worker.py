from fiat.models.worker import geom_worker


def test_geom_workers(geom_risk):
    model = geom_risk
    geom_worker(
        model.cfg,
        None,
        model.hazard_grid,
        1,
        model.vulnerability_data,
        model.exposure_data,
        model.exposure_geoms,
        model.chunks[0],
        None,
    )