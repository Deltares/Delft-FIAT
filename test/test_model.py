from fiat import Configurations, GeomModel, GridModel


def test_geommodel(tmp_path, settings_files):
    cfg = Configurations.from_file(settings_files["geom_event"])

    # With no config file
    no_cfg = Configurations(_root=tmp_path)
    model = GeomModel(no_cfg)
    assert model.exposure_data is None
    assert model.hazard_grid is None
    assert model.vulnerability_data is None
    assert len(model.exposure_geoms) == 0
    assert model.threads == 1
    assert model.cfg.get("output.path").name == "output"
    model.read_hazard_grid(path=cfg.get("hazard.file"))
    assert model.hazard_grid is not None
    assert model.hazard_grid.shape == (10, 10)
    model.read_exposure_geoms(paths=[cfg.get("exposure.geom.file1")])
    assert model.exposure_geoms[1].size == 4

    model = GeomModel(cfg)
    assert model.exposure_data is not None
    assert len(model.exposure_geoms) == 1

    _ = cfg.pop("exposure.csv.file")
    cfg.set("global.threads", 4)
    model = GeomModel(cfg)
    assert model.exposure_data is None
    assert model.threads == 4


def test_gridmodel(tmp_path, settings_files):
    cfg = Configurations.from_file(settings_files["grid_event"])

    # Without config file
    no_cfg = Configurations(_root=tmp_path)
    model = GridModel(no_cfg)
    assert model.exposure_grid is None
    assert model.hazard_grid is None
    assert model.vulnerability_data is None
    model.read_vulnerability_data(cfg.get("vulnerability.file"))
    model.read_exposure_grid(cfg.get("exposure.grid.file"))

    cfg = Configurations.from_file(settings_files["grid_event"])
    model = GridModel(cfg)
    assert model.exposure_grid is not None
    assert model.vulnerability_data is not None
