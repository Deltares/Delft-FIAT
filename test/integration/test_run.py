import math
from pathlib import Path
from typing import Callable

import numpy as np
import pytest

from fiat.error import FIATDataError
from fiat.model import GeomModel, GridModel
from fiat.open import open_geom, open_grid
from fiat.settings import GeomSettings, GridSettings

MODEL_SETTINGS = [
    "geom_2d",
    "geom_2d_risk",
    "geom_event",
    "geom_event_2g",
    "geom_event_outside",
    "geom_risk",
    "geom_risk_2g",
    "geom_uniform",
    "grid_2d",
    "grid_cat",
    "grid_cat_uniform",
    "grid_cat_variables",
    "grid_event",
    "grid_multi_combined",
    "grid_multi_separate",
    "grid_override",
    "grid_risk",
    "grid_uniform",
    "grid_uniform_risk",
    "grid_unequal",
]


def log_base(b: float, x: float) -> float:
    # Like generate.py, the curve value (not capped) of the test data
    return math.log(x) / math.log(b)


def curve_2d(b: float, depth: float, d0: float, d1: float, t: float) -> float:
    # Bilinear interpolation of the 2D test curves (generate.py, curve_2d) between
    # the depths d0 and d1 for a duration t between 2 and 5 (axis 0, 1, 2, 5, 10)
    f0, f1 = (min(log_base(b, d), 0.96) for d in (d0, d1))
    g = f0 + (depth - d0) / (d1 - d0) * (f1 - f0)
    h = 0.6 + (t - 2) / 3 * (0.75 - 0.6)
    return g * h


# Spot checks per settings file: (output file, band/ column, cell or object id,
# hand computed value). Grid depth at cell (row, col): 3.6 - 0.2 * (row + col),
# times the return period factor (1.5, 1.8, 1.9, 1.95) for risk. 1D curves are
# rounded to 2 decimals, 2D curves are not.
SPOT_CHECKS = {
    # fp_1: depth 3.4, struct_1 (log5) .76 between .73 (3.25) and .78 (3.5)
    "geom_event": ("spatial.fgb", "damage_structure_1", 1, 1000 * 0.76),
    # fp_1: depth 3.4, duration 3.0, struct_1 2D curve
    "geom_2d": (
        "spatial.fgb",
        "damage_structure_1",
        1,
        1000 * curve_2d(5, 3.4, 3.25, 3.5, 3),
    ),
    # fp_1, rp 2: depth 5.1 (clamped at 5.0, .96), duration 1.0 -> .5 + 1 / 20
    "geom_2d_risk": ("spatial_types.fgb", "affected_structure_2", 1, 100 * 0.96 * 0.55),
    # Like geom_2d, the duration from the uniform layer (3.0)
    "geom_uniform": (
        "spatial.fgb",
        "damage_structure_1",
        1,
        1000 * curve_2d(5, 3.4, 3.25, 3.5, 3),
    ),
    # fp_1: 960 for every return period, the ead is 960 / 2 (smallest rp 2)
    "geom_risk": ("spatial.fgb", "ead", 1, 960 / 2),
    # exposure1 (0, 1): depth 3.4, struct_1 2D curve, duration 3.0
    "grid_2d": (
        "output.tif",
        "exposure1_1",
        (0, 1),
        2200 * curve_2d(5, 3.4, 3.25, 3.5, 3),
    ),
    # Category 1 at (0, 1), exposure_values2 is 2500, depth 3.4 -> .76
    "grid_cat": ("output.tif", "exposure_values2_1", (0, 1), 2500 * 0.76),
    # Uniform category 1 (exposure_values 5000) at (0, 0), depth 3.6 -> .796
    "grid_cat_uniform": ("output.tif", "exposure_values_1", (0, 0), 5000 * 0.796),
    # exposure_values2 linked to default_2d, category 1 (2500) at (0, 1)
    "grid_cat_variables": (
        "output.tif",
        "exposure_values2_1",
        (0, 1),
        2500 * curve_2d(5, 3.4, 3.25, 3.5, 3),
    ),
    # (0, 1): depth 3.4 -> struct_1 .76
    "grid_event": ("output.tif", "exposure1_1", (0, 1), 2200 * 0.76),
    # exposure2 (0, 1): direct struct_2 .96 (depth 3.4) x indirect struct_2 .96
    # (duration 3.0, log3(3) = 1 capped)
    "grid_multi_combined": ("output.tif", "exposure2_1", (0, 1), 3100 * 0.96 * 0.96),
    # (0, 1): exposure1 default .76, exposure2 default .96 and default_2d .96 x .65
    "grid_multi_separate": (
        "output.tif",
        "total_1",
        (0, 1),
        2200 * 0.76 + 3100 * 0.96 + 3100 * 0.96 * 0.65,
    ),
    # exposure1 (0, 1) with struct_2 (override, file has struct_1): .96 x .65
    "grid_override": ("output.tif", "exposure1_1", (0, 1), 2200 * 0.96 * 0.65),
    # exposure1 (1, 5), rp 5: depth 2.4 x 1.8 = 4.32 -> .90 + .28 x .03
    "grid_risk": ("output.tif", "exposure1_5", (1, 5), 3500 * 0.9084),
    # exposure3 (uniform 1500) at (0, 0): depth 3.6, uniform duration 3.0
    "grid_uniform": (
        "output.tif",
        "exposure3_1",
        (0, 0),
        1500 * curve_2d(5, 3.6, 3.5, 3.75, 3),
    ),
    # exposure2 (0, 1), rp 5: depth 6.12 (clamped, .96), uniform duration 2.0
    # -> log3(2) .63
    "grid_uniform_risk": ("output.tif", "exposure2_5", (0, 1), 3100 * 0.96 * 0.63),
}


def spot_value(output_dir: Path, file: str, name: str, location) -> float:
    path = Path(output_dir, file)
    # Geometry output, per object id
    if path.suffix == ".fgb":
        with open_geom(path) as reader:
            for ft in reader:
                if ft.get_field("object_id") == location:
                    return ft.get_field(name)
        raise AssertionError(f"No feature with object_id={location}")
    # Grid output, per cell
    reader = open_grid(path)
    try:
        data = reader[reader.names.index(name)].load()
        return float(np.asarray(data)[location])
    finally:
        reader.close()


@pytest.mark.parametrize("settings_name", MODEL_SETTINGS)
def test_model_run(
    tmp_path: Path,
    model_settings: Callable[[str], GeomSettings | GridSettings],
    settings_name: str,
):
    # Get the settings
    settings = model_settings(f"{settings_name}.toml")
    output_dir = tmp_path / settings_name
    settings.update(output_dir=output_dir)
    if isinstance(settings, GeomSettings):
        model = GeomModel(settings)
    else:
        model = GridModel(settings)
    model.run()
    model.close()

    # Assert the output was written
    if isinstance(settings.output, list):
        for item in settings.output:
            assert item.file.is_file()
    else:
        assert settings.output.file.is_file()

    # Spot check a value against a hand computed one
    if settings_name not in SPOT_CHECKS:
        return
    file, name, location, expected = SPOT_CHECKS[settings_name]
    value = spot_value(output_dir, file, name, location)
    assert value == pytest.approx(expected, rel=1e-5)


def test_run_missing_variable(
    model_settings: Callable[[str], GridSettings],
):
    # Get the settings, a hazard variable 'nope' not in the file
    settings = model_settings("grid_missing_variable.toml")

    # Assert the error when building the model
    with pytest.raises(FIATDataError, match="nope"):
        GridModel(settings)
