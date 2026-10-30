"""Runtime meta module."""

from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any, Callable

from fiat._core import Interp1D
from fiat.check import (
    check_exp_columns,
    check_exp_derived_types,
    check_exp_grid_fn,
    check_hazard_identifier,
    check_hazard_rp,
    check_hazard_types,
)
from fiat.driver import NetcdfReader, Table
from fiat.method.ead import fn_density
from fiat.model.geom_util import discover_exp_columns, generate_output_columns
from fiat.typing import MethodType
from fiat.util import EAD, FN, RP, TOTAL, TYPE


@dataclass
class RunMeta:
    """Small container for geometry configuration metadata."""

    risk: bool
    type: str
    type_length: int


def get_run_meta(
    risk: bool,
    method: MethodType,
) -> RunMeta:
    """Derive the meta data from the config file for the geom calculations."""
    # Setup the meta
    meta = RunMeta(
        risk=risk,
        type=method.NAME,
        type_length=len(method.TYPES),
    )
    return meta


@dataclass
class VulnerabilityMeta:
    """Small container for some vulnerability metadata."""

    fn: dict[str, Callable[[float], float]]
    fn_list: list[str] | tuple[str]
    min: float | int
    max: float | int


def get_vulnerability_meta(
    vulnerability: Table,
) -> VulnerabilityMeta:
    """Obtain some metadata from the vulnerability data."""
    imin = min(vulnerability.index)
    imax = max(vulnerability.index)
    fn_list = vulnerability.columns
    fn = {
        item: Interp1D(vulnerability.index, vulnerability[:, item]) for item in fn_list
    }
    meta = VulnerabilityMeta(
        fn=fn,
        fn_list=fn_list,
        min=imin,
        max=imax,
    )
    return meta


@dataclass
class HazardMeta:
    """Small container for exposure metadata."""

    density: list[float | int]
    ids: list[str]
    indices_run: list[list[int]]
    indices_type: list[list[str]]
    length: int
    rp: list[float]


def get_hazard_meta(
    hazard: NetcdfReader,
    risk: bool,
    method_types: list[str],
) -> HazardMeta:
    """Obtain some metadata from the hazard data."""
    # Get the types from the metadata
    types = [band.get_attr(TYPE) for band in hazard]
    # Check the typing
    indices_type = check_hazard_types(
        types,
        method_types,
    )

    # Get the identifiers:
    identifier = None if not risk else RP
    ids = [str(idx + 1) for idx, _ in enumerate(indices_type[0])]
    ids_list = [ids] * len(indices_type)

    # If identifier is not None
    if identifier is not None:
        ids, ids_list = check_hazard_identifier(
            [band.get_attr(identifier) for band in hazard],
            indices_type=indices_type,
        )

    # Look at risk specific info
    d = None
    rp = None
    if risk:
        rp = check_hazard_rp(ids)
        d = fn_density(rp)

    # Set the grouped indices
    indices_run = [
        [indices_type[idx][item.index(idi)] for idx, item in enumerate(ids_list)]
        for idi in ids
    ]

    # Fill in the meta
    meta = HazardMeta(
        density=d,
        ids=ids,
        indices_run=indices_run,
        indices_type=indices_type,
        length=len(ids),
        rp=rp,
    )
    return meta


@dataclass
class ExposureGeomData:
    """Small container for exposure geometry data and settings."""

    area_method: str
    data: Any
    impact_types: list[str]
    path: Path
    zonal_method: str

    def __hash__(self):
        return hash(self.data)


@dataclass
class ExposureGeomMeta:
    """Small container for exposure geometry metadata."""

    area_method: str
    indices_impact: dict[str, Any]
    indices_new: list[int]
    indices_spec: list[int]
    indices_total: dict[str, list[int]]
    indices_type: dict[str, Any]
    new: list[str]
    new_length: int
    type_length: int
    zonal_method: str


def get_exposure_geom_meta(
    exposure: ExposureGeomData,
    run_meta: RunMeta,
    hazard_meta: HazardMeta,
    method: MethodType,
):
    """Simple method for sorting out the exposure meta."""  # noqa: D401
    # Check the columns validity
    columns = exposure.data.profile.columns
    mandatory_columns = method.COLUMNS
    # Check the exposure column headers
    check_exp_columns(
        list(columns.keys()),
        mandatory_columns=mandatory_columns,
    )
    indices_spec = [columns[item] for item in mandatory_columns]

    # Check the found columns
    indices_type = {}
    length_type = {}
    type_dict = {}
    for t in exposure.impact_types:
        indices_type[t] = {}
        found, found_idx, missing = discover_exp_columns(columns, type=t)
        check_exp_derived_types(t, found, missing)
        indices_type[t] = found_idx
        length_type[t] = len(found)
        type_dict[t] = found

    # The length of columns per hazard
    type_length = (
        run_meta.type_length
        + sum([len(item) for item in type_dict.values()])
        + len(type_dict)
    )

    ## Names of the new columns
    extra = []
    if run_meta.risk:
        extra = [EAD]
    new = generate_output_columns(
        method.NEW_COLUMNS,
        type_dict,
        hazard_ids=hazard_meta.ids,
        extra=extra,
    )

    # Indices of colums during calculation
    offset = run_meta.type_length
    indices_impact = {}
    indices_total = {}
    for key, value in length_type.items():
        indices_impact[key] = list(
            zip(
                *[
                    range(offset + i, len(new), type_length)[: hazard_meta.length]
                    for i in range(value)
                ]
            )
        )
        indices_total[key] = list(range(offset + value, len(new), type_length))[
            : hazard_meta.length
        ]
        offset += value + 1

    # Set the indices for the outgoing columns
    indices_new = list(range(len(columns), len(columns) + len(new)))

    # Create the exposure meta struct
    meta = ExposureGeomMeta(
        area_method=exposure.area_method,
        indices_impact=indices_impact,
        indices_new=indices_new,
        indices_spec=indices_spec,
        indices_total=indices_total,
        indices_type=indices_type,
        new=new,
        new_length=len(new),
        type_length=type_length,
        zonal_method=exposure.zonal_method,
    )
    return meta


@dataclass
class ExposureGridMeta:
    """Small container for exposure grid metadata."""

    fn_list: list[str]
    indices_new: list[list[int]]
    indices_total: list[int]
    nb: int
    new: list[str]
    index_ead: int | None = None


def get_exposure_grid_meta(
    exposure: NetcdfReader,
    run_meta: RunMeta,
    hazard_meta: HazardMeta,
    vulnerability_meta: VulnerabilityMeta,
) -> ExposureGridMeta:
    """Simple method for sorting out the exposure grid meta."""  # noqa : D401
    # Check if all impact functions are correct
    fn_list = [item.get_attr(FN) for item in exposure]
    check_exp_grid_fn(
        fn_list=fn_list,
        fn_available=vulnerability_meta.fn_list,
    )

    # Get the new band names
    new = ["_".join(c) for c in product(exposure.names, hazard_meta.ids)]
    new += [f"{TOTAL}_{idi}" for idi in hazard_meta.ids]

    # Setup from indices
    indices_new = [
        [s + hazard_meta.length * i for i in range(exposure.size)]
        for s in range(hazard_meta.length)
    ]
    indices_total = list(
        range(
            hazard_meta.length * exposure.size,
            hazard_meta.length * exposure.size + hazard_meta.length,
        )
    )
    index_ead = None
    if run_meta.risk:
        index_ead = len(new)
        new += [EAD]

    # Set up the meta
    meta = ExposureGridMeta(
        fn_list=fn_list,
        index_ead=index_ead,
        indices_new=indices_new,
        indices_total=indices_total,
        nb=len(new),
        new=new,
    )
    return meta
