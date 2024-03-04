from fiat.cfg import ConfigReader


def test_settings(settings_files):
    ConfigReader(settings_files["geom_event"])
    pass
