from pathlib import Path

from fiat import FIAT
from fiat.io import open_csv
from osgeo import gdal


def run_model(cfg, tmpdir):
    # Execute
    cfg.set_output_dir(str(tmpdir))
    mod = FIAT(cfg)
    mod.run()


def test_geom_event(tmpdir, configs):
    # run the model
    run_model(configs["geom_event"], tmpdir)

    # Check the output for this specific case
    out = open_csv(Path(str(tmpdir), "output.csv"), index="Object ID")
    assert int(float(out[2, "Total Damage"])) == 740
    assert int(float(out[3, "Total Damage"])) == 1038


def test_geom_missing(tmpdir, configs):
    # run the model
    run_model(configs["geom_event_missing"], tmpdir)

    # Check the output for this specific case
    assert Path(str(tmpdir), "missing.log").exists()
    missing = open(Path(str(tmpdir), "missing.log"), "r")
    assert sum(1 for _ in missing) == 1


def test_geom_risk(tmpdir, configs):
    # run the model
    run_model(configs["geom_risk"], tmpdir)

    # Check the output for this specific case
    out = open_csv(Path(str(tmpdir), "output.csv"), index="Object ID")
    assert int(float(out[2, "Damage: Structure (5Y)"])) == 1804
    assert int(float(out[4, "Total Damage (10Y)"])) == 3840
    assert int(float(out[3, "Risk (EAD)"]) * 100) == 102247


def test_grid_event(tmpdir, configs):
    # run the model
    run_model(configs["grid_event"], tmpdir)

    # Check the output for this specific case
    src = gdal.OpenEx(
        str(Path(str(tmpdir), "output.nc")),
    )
    arr = src.ReadAsArray()
    src = None
    assert int(arr[2, 4] * 10) == 14091
    assert int(arr[7, 3] * 10) == 8700

    src = gdal.OpenEx(
        str(Path(str(tmpdir), "total_damages.nc")),
    )
    arr = src.ReadAsArray()
    src = None
    assert int(arr[2, 4] * 10) == 14091
    assert int(arr[7, 3] * 10) == 8700


def test_grid_risk(tmpdir, configs):
    # run the model
    run_model(configs["grid_risk"], tmpdir)

    # Check the output for this specific case
    src = gdal.OpenEx(
        str(Path(str(tmpdir), "ead.nc")),
    )
    arr = src.ReadAsArray()
    src = None
    assert int(arr[1, 2] * 10) == 10920
    assert int(arr[5, 6] * 10) == 8468

    src = gdal.OpenEx(
        str(Path(str(tmpdir), "ead_total.nc")),
    )
    arr = src.ReadAsArray()
    src = None
    assert int(arr[1, 2] * 10) == 10920
    assert int(arr[5, 6] * 10) == 8468
