from pathlib import Path

import pytest
from scipy.interpolate import make_interp_spline

from fiat.cfg import Configurations
from fiat.method.ead import fn_density
from fiat.struct import Table
from fiat.struct.container import (
    ExposureGeomMeta,
    ExposureGridMeta,
    HazardMeta,
    VulnerabilityMeta,
)


@pytest.fixture
def config_empty(tmp_path: Path) -> Configurations:
    c = Configurations(_root=tmp_path)
    assert c.path == tmp_path
    return c


@pytest.fixture
def config_read_geom(
    config: Configurations,
) -> Configurations:
    config.set(
        "exposure.geom",
        [
            {"file": "exposure/spatial.geojson"},
            {"file": "exposure/spatial2.geojson"},
        ],
    )
    return config


@pytest.fixture
def config_read_grid(
    config: Configurations,
) -> Configurations:
    config.set("exposure.grid.file", "exposure/spatial.nc")
    config.set("exposure.grid.settings.var_as_band", True)
    return config


@pytest.fixture
def config_run_geom(
    config_empty: Configurations,
) -> Configurations:
    config_empty.set("hazard.type", "flood")
    config_empty.set("vulnerability.step_size", 0.01)
    config_empty.setup_output_dir()
    return config_empty


@pytest.fixture(scope="session")
def density():
    coef = fn_density(rp=[2, 5, 10, 25])
    return coef


@pytest.fixture(scope="session")
def exposure_geom_meta_run() -> ExposureGeomMeta:
    meta = ExposureGeomMeta(
        indices_new=[5, 6, 7],
        indices_spec=[2],
        indices_total=[-1],
        indices_type={"damage": {"fn": {"_structure": 3}, "max": {"_structure": 4}}},
        new=["depth_Band1", "damage_structure_Band1", "total_damage_Band1"],
        type_length=3,
    )
    return meta


@pytest.fixture(scope="session")
def exposure_grid_meta_run() -> ExposureGridMeta:
    meta = ExposureGridMeta(
        fn_list=["struct_1", "struct_2"],
        indices_new=[[0, 1]],
        indices_total=[2],
        nb=3,
        new=["band1_1", "band2_1", "total_1"],
    )
    return meta


@pytest.fixture(scope="session")
def hazard_meta_run():
    meta = HazardMeta(
        density=None,
        ids=["1"],
        indices_run=[[0]],
        indices_type=[[0]],
        length=1,
        rp=None,
        risk=False,
        type="flood",
        type_length=1,
    )
    return meta


@pytest.fixture(scope="session")
def hazard_risk_meta_run(density: list):
    meta = HazardMeta(
        density=density,
        ids=["2", "5", "10", "25"],
        indices_run=[[0], [1], [2], [3]],
        indices_type=[[0, 1, 2, 3]],
        length=4,
        rp=[2, 5, 10, 25],
        risk=True,
        type="flood",
        type_length=1,
    )
    return meta


@pytest.fixture(scope="session")
def vulnerability_data_run(vulnerability_data: Table) -> Table:
    new = vulnerability_data.upscale(delta=0.01)
    return new


@pytest.fixture(scope="session")
def vulnerability_meta_run(vulnerability_data: Table) -> ExposureGeomMeta:
    fn_list = ["struct_1", "struct_2"]
    fn = {
        item: make_interp_spline(
            vulnerability_data.index,
            vulnerability_data[:, item],
            k=1,
        )
        for item in fn_list
    }
    meta = VulnerabilityMeta(
        fn=fn,
        fn_list=fn_list,
        min=0,
        max=5,
    )
    return meta
