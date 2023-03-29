from delft_fiat.gis import overlay, geom, grid
from delft_fiat.io import open_geom, open_grid

import pytest
from numpy import mean


def test_clip_grid_geom(gm, gr):
    for ft in gm:
        hazard = overlay.clip(
            gr.src,
            gr[1],
            ft,
        )

    assert len(hazard) == 7
    assert round(mean(hazard), 2) == 1.71


def test_pin(gm, gr):
    for ft in gm:
        XY = geom.point_in_geom(ft)

        hazard = overlay.pin(
            gr.src,
            gr[1],
            XY,
        )

    assert hazard[0] == 2


def test_reproject(tmpdir, gm, gr):
    dst_crs = "EPSG:3857"

    new_gm = geom.reproject(
        gm,
        dst_crs,
        str(tmpdir),
    )

    new_gr = grid.reproject(
        gr,
        dst_crs,
        str(tmpdir),
    )

    assert new_gm.get_srs().GetAuthorityCode(None) == "3857"
    assert new_gr.get_srs().GetAuthorityCode(None) == "3857"
