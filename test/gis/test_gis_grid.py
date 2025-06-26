from pathlib import Path

import numpy as np

from fiat.fio import GridIO
from fiat.gis.grid import reproject
from fiat.util import get_srs_repr


def test_reproject(tmp_path: Path, hazard_event_repr: GridIO):
    # Assert the current state
    assert get_srs_repr(hazard_event_repr.srs) == "EPSG:4326"
    np.testing.assert_array_almost_equal(
        hazard_event_repr.bounds,
        (0, 10.0, 0, 10.0),
    )

    # Call the function
    gs = reproject(hazard_event_repr, dst_srs="EPSG:3857", out_dir=tmp_path)

    # Assert the output
    assert get_srs_repr(gs.srs) == "EPSG:3857"
    np.testing.assert_array_almost_equal(
        gs.bounds,
        (7.275958e-12, 1.116046e06, 2.843901e03, 1.118890e06),
        decimal=1,
    )


def test_reproject_resample(tmp_path: Path, hazard_event_repr: GridIO):
    # Assert the current state
    assert get_srs_repr(hazard_event_repr.srs) == "EPSG:4326"
    np.testing.assert_array_almost_equal(
        hazard_event_repr.bounds,
        (0, 10.0, 0, 10.0),
    )
    assert hazard_event_repr.shape == (10, 10)

    # Setup the gtf
    gtf = list(hazard_event_repr.geotransform)
    gtf[1] = 2.0
    gtf[5] = -2.0

    # Call the function
    gs = reproject(
        hazard_event_repr,
        dst_srs="EPSG:4326",
        dst_gtf=gtf,
        dst_height=5,
        dst_width=5,
        out_dir=Path(tmp_path, "unknown"),
    )

    # Assert the output
    assert get_srs_repr(gs.srs) == "EPSG:4326"
    np.testing.assert_array_almost_equal(
        gs.bounds,
        (0, 10.0, 0, 10.0),
    )
    assert gs.shape == (5, 5)


def test_reproject_tif(
    hazard_tif: GridIO,
):
    # Assert the current state
    assert get_srs_repr(hazard_tif.srs) == "EPSG:4326"
    np.testing.assert_array_almost_equal(
        hazard_tif.bounds,
        (0, 10.0, 0, 10.0),
    )
    assert hazard_tif.shape == (10, 10)

    # Call the function
    gs = reproject(hazard_tif, dst_srs="EPSG:3857")

    # Assert the output
    assert get_srs_repr(gs.srs) == "EPSG:3857"
    np.testing.assert_array_almost_equal(
        gs.bounds,
        (7.275958e-12, 1.116046e06, 2.843901e03, 1.118890e06),
        decimal=1,
    )
