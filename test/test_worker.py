from pathlib import Path

import pytest
from fiat.models.worker import (
    geom_resolve,
    geom_worker,
    grid_worker_exact,
    grid_worker_risk,
)


@pytest.mark.dependency()
def test_geom_worker(tmp_path, geom_risk):
    # Set model output directory
    model = geom_risk
    model.cfg.set_output_dir(Path(str(tmp_path), "..", "worker_geom"))

    # Create the files:
    model._setup_output_files()

    # Invoke the worker directly
    for idx in range(model.hazard_grid.size):
        geom_worker(
            model.cfg,
            None,
            model.hazard_grid,
            idx + 1,
            model.vulnerability_data,
            model.exposure_data,
            model.exposure_geoms,
            model.chunks[0],
            None,
        )

    # Assert output
    files = list(model.cfg.get("output.tmp.path").iterdir())
    assert len(files) == 4
    # List of files check
    expected_files = [f"{idx:03d}.dat" for idx in range(1, 5)]
    output_files = [_f.name for _f in files]
    assert sorted(output_files) == expected_files


@pytest.mark.dependency(depends=["test_geom_worker"])
def test_geom_resolve(tmp_path, geom_risk):
    # Set model output directory
    model = geom_risk
    model.cfg.set_output_dir(Path(str(tmp_path), "..", "worker_geom"))

    # Invoke the worker directly
    geom_resolve(
        model.cfg,
        model.exposure_data,
        model.exposure_geoms,
        model.chunks[0],
        None,
        None,
    )

    # Assert the output
    assert Path(model.cfg.get("output.path"), "output.csv").exists()
    assert Path(model.cfg.get("output.path"), "spatial.gpkg").exists()


@pytest.mark.dependency()
def test_grid_worker(tmp_path, grid_risk):
    # Set model output directory
    model = grid_risk
    model.cfg.set_output_dir(Path(str(tmp_path), "..", "worker_grid"))

    for idx in range(model.hazard_grid.size):
        grid_worker_exact(
            model.cfg,
            model.hazard_grid,
            idx + 1,
            model.vulnerability_data,
            model.exposure_grid,
        )

    # Assert the output
    files = list(model.cfg.get("output.damages.path").iterdir())
    assert len(files) == 8


@pytest.mark.dependency(depends=["test_grid_worker"])
def test_grid_risk_worker(tmp_path, grid_risk):
    # Set model output directory
    model = grid_risk
    model.cfg.set_output_dir(Path(str(tmp_path), "..", "worker_grid"))

    grid_worker_risk(
        model.cfg,
        model.exposure_grid.chunk,
    )

    # Assert the output
    assert Path(model.cfg.get("output.path"), "ead.nc").exists()
    assert Path(model.cfg.get("output.path"), "ead_total.nc").exists()
