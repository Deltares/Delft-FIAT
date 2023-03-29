from delft_fiat.cfg import ConfigReader

import pytest
from pathlib import Path


def test_settings():
    c = ConfigReader(Path(Path.cwd(), ".testdata", "settings.toml"))
    pass
