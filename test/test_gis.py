from fiat.gis import geom, grid, overlay
from numpy import mean


def test_clip_grid_geom(geom_data, grid_event_data):
    for ft in geom_data:
        hazard = overlay.clip(
            grid_event_data[1],
            grid_event_data.get_srs(),
            grid_event_data.get_geotransform(),
            ft,
        )

    assert len(hazard) == 7
    assert int(round(mean(hazard) * 100, 0)) == 166


def test_pin(geom_data, grid_event_data):
    for ft in geom_data:
        XY = geom.point_in_geom(ft)

        hazard = overlay.pin(
            grid_event_data[1],
            grid_event_data.get_geotransform(),
            XY,
        )

    assert int(round(hazard[0] * 100, 0)) == 160


def test_reproject(tmp_path, geom_data, grid_event_data):
    dst_crs = "EPSG:3857"

    new_gm = geom.reproject(
        geom_data,
        dst_crs,
        out_dir=str(tmp_path),
    )

    new_gr = grid.reproject(
        grid_event_data,
        dst_crs,
        out_dir=str(tmp_path),
    )

    assert new_gm.get_srs().GetAuthorityCode(None) == "3857"
    assert new_gr.get_srs().GetAuthorityCode(None) == "3857"
