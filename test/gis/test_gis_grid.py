from pathlib import Path

import numpy as np
from pyproj import Transformer

from fiat.fio import Dataset
from fiat.gis.grid import default_transform, reproject, transform_bounds
from fiat.util import get_crs_repr


def test_default_transform(hazard_event_repr: Dataset):
    # Assert the current transform
    shape = hazard_event_repr.shape_xy
    transform = hazard_event_repr.transform
    assert transform == (0.0, 1.0, 0.0, 10.0, 0.0, -1.0)

    # Call the function
    gtf, w, h = default_transform(
        transform=hazard_event_repr.transform,
        width=shape[0],
        height=shape[1],
        transformer=Transformer.from_crs(
            hazard_event_repr.crs,
            "EPSG:3857",
            always_xy=True,
        ),
        n_samples=21,
    )
    # Assert the output
    np.testing.assert_array_almost_equal(
        gtf,
        (0.0, 111605, 0.0, 1118890, 0.0, -111605),
        decimal=0,
    )
    assert w == 10  # Shocker
    assert h == 10


def test_reproject(tmp_path: Path, hazard_event_repr: Dataset):
    # Assert the current state
    assert get_crs_repr(hazard_event_repr.crs) == "EPSG:4326"
    np.testing.assert_array_almost_equal(
        hazard_event_repr.bounds,
        (0, 0, 10.0, 10.0),
    )

    # Call the function
    ds = reproject(hazard_event_repr, dst_crs="EPSG:3857", output_dir=tmp_path)

    # Assert the output
    assert get_crs_repr(ds.crs) == "EPSG:3857"
    np.testing.assert_array_almost_equal(
        ds.bounds,
        (7.275958e-12, 2.843901e03, 1.116046e06, 1.118890e06),
        decimal=1,
    )


def test_reproject_resample(tmp_path: Path, hazard_event_repr: Dataset):
    # Assert the current state
    assert get_crs_repr(hazard_event_repr.crs) == "EPSG:4326"
    np.testing.assert_array_almost_equal(
        hazard_event_repr.bounds,
        (0, 0, 10.0, 10.0),
    )
    assert hazard_event_repr.shape == (10, 10)

    # Setup the gtf
    gtf = list(hazard_event_repr.transform)
    gtf[1] = 2.0
    gtf[5] = -2.0

    # Call the function
    ds = reproject(
        hazard_event_repr,
        dst_crs="EPSG:4326",
        dst_gtf=gtf,
        dst_height=5,
        dst_width=5,
        output_dir=tmp_path,
    )

    # Assert the output
    assert get_crs_repr(ds.crs) == "EPSG:4326"
    np.testing.assert_array_almost_equal(
        ds.bounds,
        (0, 0, 10.0, 10.0),
    )
    assert ds.shape == (5, 5)


def test_transform_bounds(hazard_event_repr: Dataset):
    # Call the function
    b = transform_bounds(
        bounds=hazard_event_repr.bounds,
        transformer=Transformer.from_crs(
            hazard_event_repr.crs,
            "EPSG:3857",
            always_xy=True,
        ),
    )

    # Assert the output
    np.testing.assert_array_almost_equal(
        # Last number should match the y-origin of the default transform test
        b,
        (0.0, 0.0, 1113195, 1118890),
        decimal=0,
    )
