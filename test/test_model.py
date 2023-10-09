from fiat.io import open_csv
from fiat.models import GeomModel, GridModel

from osgeo import gdal
from pathlib import Path


def test_geom_model(tmpdir, cfg_event):
    cfg_event.set_output_dir(str(tmpdir))
    model = GeomModel(cfg_event)
    model.run()

    # check the output
    out = open_csv(Path(str(tmpdir), "output.csv"), index="Object ID")
    assert float(out[2, "Total Damage"]) == 740
    assert float(out[3, "Total Damage"]) == 1038


def test_geom_missing(tmpdir, cfg_event_mis):
    cfg_event_mis.set_output_dir(str(tmpdir))
    model = GeomModel(cfg_event_mis)
    model.run()

    assert Path(str(tmpdir), "missing.log").exists()
    missing = open(Path(str(tmpdir), "missing.log"), "r")
    assert sum(1 for _ in missing) == 1


def test_geom_risk(tmpdir, cfg_risk):
    cfg_risk.set_output_dir(str(tmpdir))
    model = GeomModel(cfg_risk)
    model.run()

    out = open_csv(Path(str(tmpdir), "output.csv"), index="Object ID")
    assert float(out[2, "Damage: Structure (5Y)"]) == 1804
    assert float(out[4, "Total Damage (10Y)"]) == 3840
    assert float(out[3, "Risk (EAD)"]) == 1022.47


def test_grid_model(tmpdir, cfg_grid):
    cfg_grid.set_output_dir(str(tmpdir))
    model = GridModel(cfg_grid)
    model.run()

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
