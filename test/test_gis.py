from numpy import mean

from fiat.gis import geom, grid, overlay
from fiat.gis.crs import get_srs_repr


def test_clip(geom_data, grid_event_data):
    ft = geom_data[3]
    hazard = overlay.clip(
        ft,
        grid_event_data[1],
        grid_event_data.get_geotransform(),
    )
    ft = None

    assert len(hazard) == 6
    assert int(round(mean(hazard) * 100, 0)) == 170


def test_clip_weighted(geom_data, grid_event_data):
    ft = geom_data[3]
    _, weights = overlay.clip_weighted(
        ft,
        grid_event_data[1],
        grid_event_data.get_geotransform(),
        upscale=10,
    )
    assert int(weights[0, 0] * 100) == 90

    _, weights = overlay.clip_weighted(
        ft,
        grid_event_data[1],
        grid_event_data.get_geotransform(),
        upscale=100,
    )
    assert int(weights[0, 0] * 100) == 81


def test_pin(geom_data, grid_event_data):
    for ft in geom_data:
        XY = geom.point_in_geom(ft)

        hazard = overlay.pin(
            XY,
            grid_event_data[1],
            grid_event_data.get_geotransform(),
        )

    assert int(round(hazard[0] * 100, 0)) == 160


def test_geom_reproject(tmp_path, geom_data, grid_event_data):
    dst_crs = "EPSG:3857"
    new_gm = geom.reproject(
        geom_data,
        dst_crs,
        out_dir=str(tmp_path),
    )

    assert new_gm.get_srs().GetAuthorityCode(None) == "3857"


def test_grid_reproject(tmp_path, grid_event_data):
    dst_crs = "EPSG:3857"
    new_gr = grid.reproject(
        grid_event_data,
        dst_crs,
        out_dir=str(tmp_path),
    )

    assert new_gr.get_srs().GetAuthorityCode(None) == "3857"


def test_grid_reproject_gtf(tmp_path, grid_event_data, grid_event_highres_data):
    assert grid_event_highres_data.shape == (100, 100)
    new_gr = grid.reproject(
        grid_event_highres_data,
        get_srs_repr(grid_event_data.get_srs()),
        dst_gtf=grid_event_data.get_geotransform(),
        dst_width=10,
        dst_height=10,
        out_dir=str(tmp_path),
    )

    assert new_gr.shape == (10, 10)
