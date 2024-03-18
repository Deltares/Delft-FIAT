from fiat.cfg import ConfigReader


def test_settings(settings_files):
    cfg = ConfigReader(settings_files["geom_risk"])

    # Assert path to itself
    assert cfg.filepath.name == "geom_risk.toml"

    # Assert a global setting
    assert cfg.get("global.keep_temp_files")

    # Assert generated kwargs functionality
    haz_kw = cfg.generate_kwargs("hazard.settings")
    assert "var_as_band" in haz_kw

    # Assert updating leads to extra kwargs
    cfg.set("global.is_here", True)
    assert "global.is_here" in cfg._extra_args
