from pathlib import Path

import pytest
from fiat import FIAT
from fiat.io import open_csv
from osgeo import gdal
from pytest_cov.embed import cleanup_on_sigterm

from .conftest import _MODELS


@pytest.mark.parametrize("model", _MODELS)
def test_model(tmpdir, model, configs):
    # Lets see if this works
    cleanup_on_sigterm()

    # Setup the models per model
    cfg = configs[model]
    cfg.set_output_dir(str(tmpdir))
    mod = FIAT(cfg)
    mod.run()

    # assert per model type
    if model == "geom_event":
        out = open_csv(Path(str(tmpdir), "output.csv"), index="Object ID")
        assert int(float(out[2, "Total Damage"])) == 740
        assert int(float(out[3, "Total Damage"])) == 1038

    elif model == "geom_event_missing":
        # check the output
        assert Path(str(tmpdir), "missing.log").exists()
        missing = open(Path(str(tmpdir), "missing.log"), "r")
        assert sum(1 for _ in missing) == 1

    elif model == "geom_risk":
        out = open_csv(Path(str(tmpdir), "output.csv"), index="Object ID")
        assert int(float(out[2, "Damage: Structure (5Y)"])) == 1804
        assert int(float(out[4, "Total Damage (10Y)"])) == 3840
        assert int(float(out[3, "Risk (EAD)"]) * 100) == 102247

    elif model == "grid_event":
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

    elif model == "grid_risk":
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
