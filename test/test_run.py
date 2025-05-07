import copy
from pathlib import Path

from osgeo import gdal

from fiat.fio import open_csv, open_grid
from fiat.models import GeomModel, GridModel


def run_model(cfg, p):
    # Execute
    cfg.setup_output_dir(str(p))
    model_type = cfg.get("model.model_type")
    if model_type == "geom":
        mod = GeomModel(cfg)
    elif model_type == "grid":
        mod = GridModel(cfg)
    mod.run()


def test_geom_event(tmp_path, configs):
    # run the model
    run_model(configs["geom_event"], tmp_path)

    # Check the output for this specific case
    out = open_csv(Path(str(tmp_path), "output.csv"), index="object_id")
    assert int(float(out[2, "total_damage"])) == 740
    assert int(float(out[3, "total_damage"])) == 1038


def test_geom_missing(tmp_path, configs):
    # run the model
    run_model(configs["geom_event_missing"], tmp_path)

    # Check the output for this specific case
    assert Path(str(tmp_path), "missing.log").exists()
    missing = open(Path(str(tmp_path), "missing.log"), "r")
    assert sum(1 for _ in missing) == 1


def test_geom_outside(tmp_path, configs):
    # run the model
    run_model(configs["geom_event_outside"], tmp_path)

    # Check the output for this specific case
    data = open_csv(Path(tmp_path, "output.csv"))

    assert data[0, "damage_structure"] == "nan"
    assert float(data[0, "total_damage"]) == 0.0
    assert float(data[1, "damage_structure"]) == 1804.0


def test_geom_risk(tmp_path, configs):
    # run the model
    run_model(configs["geom_risk"], tmp_path)

    # Check the output for this specific case
    out = open_csv(Path(str(tmp_path), "output.csv"), index="object_id")
    assert int(float(out[2, "damage_structure_5.0y"])) == 1804
    assert int(float(out[4, "total_damage_10.0y"])) == 3840
    assert int(float(out[3, "ead_damage"]) * 100) == 102247


def test_grid_event(tmp_path, configs):
    # run the model
    run_model(configs["grid_event"], tmp_path)

    # Check the output for this specific case
    src = gdal.OpenEx(
        str(Path(str(tmp_path), "output.nc")),
    )
    arr = src.ReadAsArray()
    src = None
    assert int(arr[2, 4] * 10) == 14092
    assert int(arr[7, 3] * 10) == 8700

    src = gdal.OpenEx(
        str(Path(str(tmp_path), "total_damages.nc")),
    )
    arr = src.ReadAsArray()
    src = None
    assert int(arr[2, 4] * 10) == 14092
    assert int(arr[7, 3] * 10) == 8700


def test_grid_unequal(tmp_path, configs):
    # Run the model
    cfg = copy.deepcopy(configs["grid_unequal"])
    run_model(cfg, tmp_path)
    # Assert the output
    file = Path(tmp_path, "output.nc")
    assert file.is_file()
    # Check the output
    gs = open_grid(file)
    assert gs.shape == (10, 10)
    gs.close()
    gs = None

    # Adjust to prefer the hazard data resolution
    cfg = copy.deepcopy(configs["grid_unequal"])
    cfg.set("model.grid.prefer", "hazard")
    run_model(cfg, tmp_path)

    # Check the output
    gs = open_grid(file)
    assert gs.shape == (100, 100)


def test_grid_risk(tmp_path, configs):
    # run the model
    run_model(configs["grid_risk"], tmp_path)

    # Check the output for this specific case
    src = gdal.OpenEx(
        str(Path(str(tmp_path), "ead.nc")),
    )
    arr = src.ReadAsArray()
    src = None
    assert int(arr[1, 2] * 10) == 10920
    assert int(arr[5, 6] * 10) == 8468

    src = gdal.OpenEx(
        str(Path(str(tmp_path), "ead_total.nc")),
    )
    arr = src.ReadAsArray()
    src = None
    assert int(arr[1, 2] * 10) == 10920
    assert int(arr[5, 6] * 10) == 8468
