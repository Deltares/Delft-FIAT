from pathlib import Path
from typing import Callable

import pytest

from fiat.model import GeomModel, GridModel
from fiat.settings import GeomSettings, GridSettings

MODEL_SETTINGS = [
    "geom_event",
    "geom_event_2g",
    "geom_event_outside",
    "geom_risk",
    "geom_risk_2g",
    "grid_event",
    "grid_risk",
    "grid_unequal",
]


@pytest.mark.parametrize("settings_name", MODEL_SETTINGS)
def test_model_run(
    tmp_path: Path,
    model_settings: Callable[[str], GeomSettings | GridSettings],
    settings_name: str,
):
    # Get the settings
    settings = model_settings(f"{settings_name}.toml")
    settings.update(output_dir=tmp_path / settings_name)
    if isinstance(settings, GeomSettings):
        model = GeomModel(settings)
    else:
        model = GridModel(settings)
    model.run()

    # Assert the output was written
    if isinstance(settings.output, list):
        for item in settings.output:
            assert item.file.is_file()
    else:
        assert settings.output.file.is_file()
