import sys
from pathlib import Path

from osgeo import osr

from fiat import ConfigReader, GeomModel, GridModel
from fiat.check import (
    check_exp_derived_types,
    check_hazard_rp,
    check_hazard_subsets,
    check_internal_srs,
)
from fiat.error import FIATDataError
from fiat.util import discover_exp_columns


def test_check_config_entries(settings_files):
    settings = settings_files["missing_hazard"]

    try:
        _ = ConfigReader(settings)
    except FIATDataError:
        t, v, tb = sys.exc_info()
        assert v.msg.startswith("Missing mandatory entries")
        assert v.msg.endswith("['hazard.file']")
    finally:
        assert v


def test_check_config_models(settings_files):
    neither = settings_files["missing_models"]
    cfg = ConfigReader(neither)
    assert cfg.get_model_type() == [False, False]

    geom = settings_files["geom_event"]
    cfg = ConfigReader(geom)
    assert cfg.get_model_type() == [True, False]

    geom = settings_files["grid_event"]
    cfg = ConfigReader(geom)
    assert cfg.get_model_type() == [False, True]


def test_check_exp_columns(configs):
    cfg = configs["geom_event"]
    cfg.set(
        "exposure.csv.file",
        Path(Path.cwd(), ".testdata", "exposure", "spatial_missing.csv"),
    )

    try:
        _ = GeomModel(cfg)
    except FIATDataError:
        t, v, tb = sys.exc_info()
        assert v.msg == "Missing mandatory exposure columns: ['object_id']"
    finally:
        assert v


def test_check_exp_derived_types(geom_partial_data):
    found, found_idx, missing = discover_exp_columns(
        geom_partial_data._columns, type="damage"
    )
    assert missing == ["content"]
    check_exp_derived_types("damage", found, missing)

    found = []
    try:
        check_exp_derived_types("damage", found, missing)
    except FIATDataError:
        t, v, tb = sys.exc_info()
        assert v.msg.startswith("For type: 'damage' no matching")
    finally:
        assert v


def test_check_exp_index_col(configs):
    cfg = configs["geom_event"]
    cfg.set("exposure.geom.settings.index", "faulty")

    try:
        _ = GeomModel(cfg)
    except FIATDataError:
        t, v, tb = sys.exc_info()
        assert v.msg.startswith("Index column ('faulty') not found")
    finally:
        assert v


def test_check_grid_exact(configs):
    exact = configs["grid_event"]
    model = GridModel(exact)
    assert model.equal == True

    unequal = configs["grid_unequal"]
    model = GridModel(unequal)
    assert model.equal == False
    assert model.cfg.get("hazard.file").exists()


def test_check_hazard_rp():
    rp_bands = ["a", "b", "c", "d"]
    rp_cfg = [1, 2, 5, 10]

    out = check_hazard_rp(rp_bands, rp_cfg, "")
    assert out == [1.0, 2.0, 5.0, 10.0]

    rp_cfg.remove(10)
    try:
        _ = check_hazard_rp(rp_bands, rp_cfg, Path("file.ext"))
    except FIATDataError:
        t, v, tb = sys.exc_info()
        assert v.msg.startswith(
            "'file.ext': cannot determine the return periods \
for the risk calculation"
        )
    finally:
        assert v


def test_check_hazard_subsets(grid_event_data, grid_risk_data):
    assert grid_event_data.subset_dict is None
    check_hazard_subsets(grid_event_data.subset_dict, "")

    try:
        assert grid_risk_data.subset_dict is not None
        check_hazard_subsets(grid_risk_data.subset_dict, Path("file.ext"))
    except FIATDataError:
        t, v, tb = sys.exc_info()
        assert v.msg.startswith("'file.ext': cannot read this file as there")
    assert v


def test_check_internal_srs():
    try:
        check_internal_srs(None, "file", None)
    except FIATDataError:
        t, v, tb = sys.exc_info()
        assert v.msg.startswith("Coordinate reference system is unknown for 'file'")
    finally:
        assert v

    s = osr.SpatialReference()
    s.ImportFromEPSG(4326)

    int_srs = check_internal_srs(s, fname="")
    assert int_srs is None
    s = None

    int_srs = check_internal_srs(None, "", "EPSG:4326")
    assert int_srs is not None
    assert int_srs.GetAuthorityCode(None) == "4326"
    int_srs = None
