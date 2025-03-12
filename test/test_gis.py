import sys

from numpy import mean

from fiat.gis import geom, grid, overlay
from fiat.util import get_srs_repr


def test_get_srs_repr(geom_data):
    out = get_srs_repr(geom_data.srs)
    assert out == "EPSG:4326"

    try:
        out = get_srs_repr(None)
    except ValueError:
        t, v, tb = sys.exc_info()
        assert v.args[0].endswith("'srs' can not be 'None'.")
    finally:
        assert v


def test_clip(geom_data, grid_event_data):
    ft = geom_data[3]
    hazard = overlay.clip(
        ft,
        grid_event_data[1],
        grid_event_data.geotransform,
    )
    ft = None

    assert len(hazard) == 6
    assert int(round(mean(hazard) * 100, 0)) == 170


def test_clip_weighted(geom_data, grid_event_data):
    ft = geom_data[3]
    _, weights = overlay.clip_weighted(
        ft,
        grid_event_data[1],
        grid_event_data.geotransform,
        upscale=10,
    )
    assert int(weights[0, 0] * 100) == 90

    _, weights = overlay.clip_weighted(
        ft,
        grid_event_data[1],
        grid_event_data.geotransform,
        upscale=100,
    )
    assert int(weights[0, 0] * 100) == 81


def test_pin(geom_data, grid_event_data):
    for ft in geom_data:
        XY = geom.point_in_geom(ft)

        hazard = overlay.pin(
            XY,
            grid_event_data[1],
            grid_event_data.geotransform,
        )

    assert int(round(hazard[0] * 100, 0)) == 160


def test_geom_reproject(tmp_path, geom_data):
    dst_crs = "EPSG:3857"
    new_gm = geom.reproject(
        geom_data,
        dst_crs,
        out_dir=str(tmp_path),
    )

    assert new_gm.srs.GetAuthorityCode(None) == "3857"


def test_geom_reproject_single(geom_data):
    ft = geom_data[1]
    geometry = ft.GetGeometryRef()

    vertices = geometry.GetGeometryRef(0).GetPoints()
    assert 4.39 < vertices[0][0] < 4.4

    geom.reproject_feature(
        geometry,
        src_crs="EPSG:4326",
        dst_crs="EPSG:28992",
    )

    vertices = geometry.GetGeometryRef(0).GetPoints()
    assert 80000 < vertices[0][0] < 90000


def test_grid_reproject(tmp_path, grid_event_data):
    dst_crs = "EPSG:3857"
    new_gr = grid.reproject(
        grid_event_data,
        dst_crs,
        out_dir=str(tmp_path),
    )

    assert new_gr.srs.GetAuthorityCode(None) == "3857"


def test_grid_reproject_gtf(tmp_path, grid_event_data, grid_event_highres_data):
    assert grid_event_highres_data.shape == (100, 100)
    new_gr = grid.reproject(
        grid_event_highres_data,
        get_srs_repr(grid_event_data.srs),
        dst_gtf=grid_event_data.geotransform,
        dst_width=10,
        dst_height=10,
        out_dir=str(tmp_path),
    )

    assert new_gr.shape == (10, 10)
