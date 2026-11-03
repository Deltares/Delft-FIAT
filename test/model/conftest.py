from collections.abc import Generator
from itertools import product
from pathlib import Path
from typing import Callable

import numpy as np
import pytest
from pyproj import CRS

from fiat.driver import FlatGeobufReader, NetcdfReader, NetcdfWriter
from fiat.method.ead import fn_density
from fiat.model.meta import (
    ExposureGeomData,
    ExposureGeomMeta,
    ExposureGridMeta,
    HazardMeta,
    RunMeta,
    VulnerabilityMeta,
    get_exposure_grid_meta,
    get_hazard_meta,
    get_vulnerability_meta,
)
from fiat.open import open_geom
from fiat.settings.variables import (
    ExposureGridVariable,
    HazardVariable,
    VulnerabilityVariable,
)
from fiat.util import DEFAULT


## Variable settings, like the ones in the generated settings files
class Vars:
    RPS = (2, 5, 10, 25)

    @staticmethod
    def vuln_1d(
        name: str = DEFAULT,
        method: str = "flood.depth",
        index: str = "depth",
        type: str = "water_depth",
    ) -> VulnerabilityVariable:
        return VulnerabilityVariable(
            name=name, method=method, types={f"{index}_{name}": type}
        )

    @staticmethod
    def vuln_2d(name: str = DEFAULT) -> VulnerabilityVariable:
        return VulnerabilityVariable(
            name=name,
            method="flood.depth_duration_2d",
            types={f"depth_{name}": "water_depth", f"duration_{name}": "duration"},
        )

    @staticmethod
    def vuln_multi() -> list[VulnerabilityVariable]:
        return [
            Vars.vuln_1d(),
            Vars.vuln_2d("default_2d"),
            Vars.vuln_1d("direct", method="flood.depth_duration"),
            Vars.vuln_1d(
                "indirect",
                method="flood.depth_duration",
                index="days",
                type="duration",
            ),
        ]

    @staticmethod
    def haz_event() -> list[HazardVariable]:
        return [HazardVariable(name="data", type="water_depth")]

    @staticmethod
    def haz_risk() -> list[HazardVariable]:
        return [
            HazardVariable(name=f"{rp}Y", type="water_depth", rp=rp) for rp in Vars.RPS
        ]

    @staticmethod
    def haz_event_duration() -> list[HazardVariable]:
        return [
            HazardVariable(name="depth", type="water_depth"),
            HazardVariable(name="duration", type="duration"),
        ]

    @staticmethod
    def haz_risk_duration() -> list[HazardVariable]:
        return [
            HazardVariable(name=f"{name}_{rp}Y", type=type, rp=rp)
            for rp in Vars.RPS
            for name, type in (("depth", "water_depth"), ("duration", "duration"))
        ]

    @staticmethod
    def exp_grid(default: str = DEFAULT, **links) -> list[ExposureGridVariable]:
        return [
            ExposureGridVariable(
                name=name,
                type=DEFAULT,
                fn_curve=curve,
                vulnerability=links.get(name, default),
            )
            for name, curve in (("exposure1", "struct_1"), ("exposure2", "struct_2"))
        ]

    @staticmethod
    def exp_cat(**kwargs) -> ExposureGridVariable:
        return ExposureGridVariable(name="exposure", type="categorized", **kwargs)

    @staticmethod
    def exp_cat_default() -> list[ExposureGridVariable]:
        # Like grid_cat.toml
        return [Vars.exp_cat()] + Vars.exp_values()

    @staticmethod
    def exp_values(*names: str, **links) -> list[ExposureGridVariable]:
        return [
            ExposureGridVariable(
                name=name,
                type="values",
                vulnerability=links.get(name, DEFAULT),
            )
            for name in names or ("exposure_values", "exposure_values2")
        ]

    @staticmethod
    def exp_grid_combined() -> list[ExposureGridVariable]:
        # Like grid_multi_combined.toml
        return Vars.exp_grid(exposure2=["direct", "indirect"])

    @staticmethod
    def exp_grid_separate() -> list[ExposureGridVariable]:
        # Like grid_multi_separate.toml
        return Vars.exp_grid(exposure2=[DEFAULT, "default_2d"])

    @staticmethod
    def exp_cat_variables() -> list[ExposureGridVariable]:
        # Like grid_cat_variables.toml
        return [
            Vars.exp_cat(values=["exposure_values", "exposure_values2"]),
            *Vars.exp_values(exposure_values2="default_2d"),
        ]

    @staticmethod
    def exp_cat_uniform() -> list[ExposureGridVariable]:
        # Like grid_cat_uniform.toml
        return [
            Vars.exp_cat(values=["exposure_values2"]),
            ExposureGridVariable(
                name="exposure_uniform",
                type="categorized",
                value=1,
                values=["exposure_values"],
            ),
            *Vars.exp_values(),
        ]


@pytest.fixture(scope="session")
def variables() -> type[Vars]:
    return Vars


## Structures
class DummyQueue:
    def put_nowait(self, item): ...


class DummyPipeline:
    def recv(self): ...


@pytest.fixture
def dummy_queue() -> DummyQueue:
    return DummyQueue()


@pytest.fixture
def dummy_pipeline() -> DummyPipeline:
    return DummyPipeline()


@pytest.fixture
def grid_handle(
    tmp_path: Path,
    crs_4326: CRS,
) -> NetcdfWriter:
    ds = NetcdfWriter(
        file=Path(tmp_path, "foo.nc"),
    )
    gtf = (0.0, 1.0, 0.0, 10.0, 0.0, -1.0)
    ny, nx = (10, 10)
    ds.create_spatial_dims(
        lats=np.arange(gtf[3] + gtf[5] * 0.5, gtf[3] + gtf[5] * ny, gtf[5]),
        lons=np.arange(gtf[0] + gtf[1] * 0.5, gtf[0] + gtf[1] * nx, gtf[1]),
    )
    ds.set_spatial_ref(crs_4326)
    ds.create_spatial_variable(var="data")
    return ds


@pytest.fixture
def open_reader() -> Generator[Callable[..., NetcdfReader], None, None]:
    # Open netcdf readers that are closed after the test
    readers: list[NetcdfReader] = []

    def _open(*args, **kwargs) -> NetcdfReader:
        readers.append(NetcdfReader(*args, **kwargs))
        return readers[-1]

    yield _open
    for item in readers:
        item.close()


## Data related
@pytest.fixture(scope="session")
def curves_2d_path(testdata_dir: Path) -> Path:
    p = Path(testdata_dir, "curves_2d.nc")
    assert p.is_file()
    return p


@pytest.fixture(scope="session")
def curves_multi_path(testdata_dir: Path) -> Path:
    p = Path(testdata_dir, "curves_multi.nc")
    assert p.is_file()
    return p


@pytest.fixture(scope="session")
def event_map_duration_path(testdata_dir: Path) -> Path:
    p = Path(testdata_dir, "event_map_duration.nc")
    assert p.is_file()
    return p


@pytest.fixture(scope="session")
def risk_map_duration_path(testdata_dir: Path) -> Path:
    p = Path(testdata_dir, "risk_map_duration.nc")
    assert p.is_file()
    return p


@pytest.fixture(scope="session")
def density():
    coef = fn_density(rp=[2, 5, 10, 25])
    return coef


@pytest.fixture(scope="session")
def exposure_geom_data_run(
    exposure_geom_data: FlatGeobufReader,
) -> ExposureGeomData:
    data = ExposureGeomData(
        area_method="area",
        data=exposure_geom_data,
        impact_types=["damage"],
        path=exposure_geom_data.path,
        vulnerability=DEFAULT,
        zonal_method="mean",
    )
    return data


@pytest.fixture(scope="session")
def exposure_geom_types_data(testdata_dir: Path) -> FlatGeobufReader:
    p = Path(testdata_dir, "exposure", "spatial_types.fgb")
    assert p.is_file()
    ds = open_geom(p)  # Read only
    assert isinstance(ds, FlatGeobufReader)
    return ds


@pytest.fixture(scope="session")
def exposure_geom_types_data_run(
    exposure_geom_types_data: FlatGeobufReader,
) -> ExposureGeomData:
    # Like geom_2d_risk.toml
    data = ExposureGeomData(
        area_method="area",
        data=exposure_geom_types_data,
        impact_types=["damage", "affected"],
        path=exposure_geom_types_data.path,
        vulnerability="default_2d",
        zonal_method="mean",
    )
    return data


@pytest.fixture(scope="session")
def exposure_geom_meta_run(vulnerability_meta: VulnerabilityMeta) -> ExposureGeomMeta:
    meta = ExposureGeomMeta(
        area_method="area",
        fn=vulnerability_meta.datasets[DEFAULT].fn,
        hazard_indices=[(0,)],
        indices_ead={},
        indices_impact={"damage": [(1,)]},
        indices_new=[5, 6, 7],
        indices_spec=[2],
        indices_total={"damage": [2]},
        indices_type={"damage": [[3, 4]]},
        method="flood.depth",
        new=["depth_1", "damage_structure_1", "total_damage_1"],
        new_length=3,
        type_length=3,
        zonal_method="mean",
    )
    return meta


@pytest.fixture(scope="session")
def exposure_geom_risk_meta_run(
    vulnerability_meta: VulnerabilityMeta,
) -> ExposureGeomMeta:
    meta = ExposureGeomMeta(
        area_method="area",
        fn=vulnerability_meta.datasets[DEFAULT].fn,
        hazard_indices=[(0,), (1,), (2,), (3,)],
        indices_ead={"damage": 12},
        indices_impact={"damage": [(1,), (4,), (7,), (10,)]},
        indices_new=list(range(5, 18, 1)),
        indices_spec=[2],
        indices_total={"damage": [2, 5, 8, 11]},
        indices_type={"damage": [[3, 4]]},
        method="flood.depth",
        new=[
            f"{y}_{x}"
            for x, y in product(
                [2, 5, 10, 25], ["depth", "damage_structure", "total_damage"]
            )
        ]
        + ["ead"],
        new_length=13,
        type_length=3,
        zonal_method="mean",
    )
    return meta


@pytest.fixture
def exposure_grid_cat_meta_run(
    exposure_grid_cat_data: NetcdfReader,
    run_meta: RunMeta,
    hazard_meta_run: HazardMeta,
    vulnerability_cat_meta: VulnerabilityMeta,
) -> ExposureGridMeta:
    return get_exposure_grid_meta(
        exposure_grid_cat_data,
        Vars.exp_cat_default(),
        run_meta=run_meta,
        hazard_meta=hazard_meta_run,
        vulnerability_meta=vulnerability_cat_meta,
    )


@pytest.fixture
def exposure_grid_meta_run(
    exposure_grid_data: NetcdfReader,
    run_meta: RunMeta,
    hazard_meta_run: HazardMeta,
    vulnerability_meta: VulnerabilityMeta,
) -> ExposureGridMeta:
    return get_exposure_grid_meta(
        exposure_grid_data,
        Vars.exp_grid(),
        run_meta=run_meta,
        hazard_meta=hazard_meta_run,
        vulnerability_meta=vulnerability_meta,
    )


@pytest.fixture
def exposure_grid_risk_meta_run(
    exposure_grid_data: NetcdfReader,
    run_risk_meta: RunMeta,
    hazard_risk_meta_run: HazardMeta,
    vulnerability_meta: VulnerabilityMeta,
) -> ExposureGridMeta:
    return get_exposure_grid_meta(
        exposure_grid_data,
        Vars.exp_grid(),
        run_meta=run_risk_meta,
        hazard_meta=hazard_risk_meta_run,
        vulnerability_meta=vulnerability_meta,
    )


@pytest.fixture
def exposure_grid_combined_data(
    exposure_grid_path: Path,
) -> Generator[NetcdfReader, None, None]:
    # Like grid_multi_combined.toml
    ds = NetcdfReader(exposure_grid_path)
    ds.load()
    yield ds
    ds.close()


@pytest.fixture
def exposure_grid_separate_data(
    exposure_grid_path: Path,
) -> Generator[NetcdfReader, None, None]:
    # Like grid_multi_separate.toml
    ds = NetcdfReader(exposure_grid_path)
    ds.load()
    yield ds
    ds.close()


@pytest.fixture
def exposure_grid_cat_variables_data(
    exposure_grid_cat_path: Path,
) -> Generator[NetcdfReader, None, None]:
    # Like grid_cat_variables.toml
    ds = NetcdfReader(exposure_grid_cat_path)
    ds.load()
    yield ds
    ds.close()


@pytest.fixture
def exposure_grid_cat_uniform_data(
    exposure_grid_cat_path: Path,
) -> Generator[NetcdfReader, None, None]:
    # Like grid_cat_uniform.toml
    ds = NetcdfReader(exposure_grid_cat_path)
    ds.add_constant("exposure_uniform", 1)
    ds.load()
    yield ds
    ds.close()


@pytest.fixture
def hazard_event_duration_data(
    event_map_duration_path: Path,
) -> Generator[NetcdfReader, None, None]:
    ds = NetcdfReader(event_map_duration_path)
    ds.load()
    yield ds
    ds.close()


@pytest.fixture(scope="session")
def hazard_meta_duration(event_map_duration_path: Path) -> HazardMeta:
    with NetcdfReader(event_map_duration_path) as ds:
        return get_hazard_meta(
            ds,
            Vars.haz_event_duration(),
            risk=False,
            method_types=["water_depth", "duration"],
        )


@pytest.fixture(scope="session")
def hazard_meta_run() -> HazardMeta:
    meta = HazardMeta(
        density=None,
        ids=["1"],
        indices_run=[[0]],
        indices_type=[[0]],
        length=1,
        rp=None,
        types=["water_depth"],
    )
    return meta


@pytest.fixture(scope="session")
def hazard_risk_meta_run(density: list) -> HazardMeta:
    meta = HazardMeta(
        density=density,
        ids=["2", "5", "10", "25"],
        indices_run=[[0], [1], [2], [3]],
        indices_type=[[0, 1, 2, 3]],
        length=4,
        rp=[2, 5, 10, 25],
        types=["water_depth"],
    )
    return meta


@pytest.fixture(scope="session")
def run_meta() -> RunMeta:
    meta = RunMeta(risk=False)
    return meta


@pytest.fixture(scope="session")
def run_risk_meta() -> RunMeta:
    meta = RunMeta(risk=True)
    return meta


# The readers are closed after deriving the metadata, as netCDF4 can crash when
# files with string coordinates are reopened while another handle is still open
@pytest.fixture(scope="session")
def vulnerability_meta(vulnerability_path: Path) -> VulnerabilityMeta:
    with NetcdfReader(vulnerability_path) as ds:
        return get_vulnerability_meta(ds, [Vars.vuln_1d()], names=[DEFAULT])


@pytest.fixture(scope="session")
def vulnerability_cat_meta(vulnerability_cat_path: Path) -> VulnerabilityMeta:
    with NetcdfReader(vulnerability_cat_path) as ds:
        return get_vulnerability_meta(
            ds,
            [Vars.vuln_1d(), Vars.vuln_2d("default_2d")],
            names=[DEFAULT, "default_2d"],
        )


@pytest.fixture(scope="session")
def vulnerability_multi_meta(curves_multi_path: Path) -> VulnerabilityMeta:
    with NetcdfReader(curves_multi_path) as ds:
        return get_vulnerability_meta(
            ds,
            Vars.vuln_multi(),
            names=[DEFAULT, "default_2d", "direct", "indirect"],
        )


@pytest.fixture(scope="session")
def vulnerability_2d_meta(curves_2d_path: Path) -> VulnerabilityMeta:
    with NetcdfReader(curves_2d_path) as ds:
        return get_vulnerability_meta(ds, [Vars.vuln_2d()], names=[DEFAULT])


# Aliases of the old fixture names, used by the grid/geom meta and worker tests
@pytest.fixture(scope="session")
def vulnerability_meta_run(vulnerability_meta: VulnerabilityMeta) -> VulnerabilityMeta:
    return vulnerability_meta


@pytest.fixture(scope="session")
def vulnerability_cat_meta_run(
    vulnerability_cat_meta: VulnerabilityMeta,
) -> VulnerabilityMeta:
    return vulnerability_cat_meta
