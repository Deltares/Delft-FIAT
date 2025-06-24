from fiat.cfg import Configurations


def test_settigs(configs):
    cfg = Configurations()
    assert len(cfg.keys()) == 1
    assert "output.path" in cfg
    assert cfg.get("output.path").name == "output"
    assert cfg.filepath.name == "< Configurations-in-memory >"

    cfg = Configurations(some_var="some_value")
    assert len(cfg.keys()) == 2
    assert "some_var" in cfg

    file = configs["geom_event"].get("hazard.file")
    cfg = Configurations(**{"hazard": {"file": file}, "some_file": "data2.dat"})
    assert len(cfg.keys()) == 3
    assert cfg.get("hazard.file").is_absolute()
    assert isinstance(cfg.get("some_file"), str)


def test_settings_from_file(settings_files):
    cfg = Configurations.from_file(settings_files["geom_risk"])

    # Assert path to itself
    assert cfg.path.name == ".testdata"
    assert cfg.filepath.name == "geom_risk.toml"

    # Assert generated kwargs functionality
    haz_kw = cfg.generate_kwargs("hazard.settings")
    assert "var_as_band" in haz_kw

    # Update
    cfg.update({"output.path": "other", "_some_var": "some_value"})
    assert cfg.get("_some_var") == "some_value"
    assert cfg.get("output.path").is_absolute()
