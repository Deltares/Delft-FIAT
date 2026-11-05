"""Runtime meta module."""

from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np

from fiat._core import Interp1D, InterpND
from fiat.check import (
    check_exp_cat_uniform,
    check_exp_cat_value,
    check_exp_cat_value_settings,
    check_exp_cat_values,
    check_exp_columns,
    check_exp_derived_types,
    check_exp_variables,
    check_hazard_identifier,
    check_hazard_rp,
    check_hazard_types,
    check_hazard_variable_rp,
    check_hazard_variables,
    check_vuln_axes,
    check_vuln_axis_types,
    check_vuln_curve_ids,
    check_vuln_grid_method,
    check_vuln_group,
    check_vuln_method,
    check_vuln_types_keys,
    check_vuln_types_missing,
    check_vuln_variables,
)
from fiat.driver import NetcdfReader
from fiat.driver.netcdf.reader import ConstantVariable
from fiat.error import FIATDataError
from fiat.method.ead import fn_density
from fiat.model.geom_util import discover_exp_columns, generate_output_columns
from fiat.settings.variables import (
    ExposureGridVariable,
    HazardVariable,
    VulnerabilityVariable,
)
from fiat.util import (
    CATEGORIZED,
    CURVE,
    DEFAULT,
    EAD,
    FIAT_METHOD,
    RP,
    TOTAL,
    VALUES,
)


@dataclass
class RunMeta:
    """Small container for the run metadata."""

    risk: bool
    cell_size: float | int = 1


def get_run_meta(
    risk: bool,
    cell_size: float | int = 1.0,
) -> RunMeta:
    """Derive the run metadata.

    Parameters
    ----------
    risk : bool
        Whether it is a risk calculation.
    cell_size : float | int, optional
        The size (area) of a grid cell, by default 1.0.

    Returns
    -------
    RunMeta
        The run metadata.
    """
    meta = RunMeta(
        cell_size=cell_size,
        risk=risk,
    )
    return meta


@dataclass
class VulnerabilityDataset:
    """Small container for the metadata of a single vulnerability dataset.

    The axes of the curve functions are ordered like the `AXIS_TYPES` of the method
    for datasets with multiple axes.
    """

    axis_types: tuple[str, ...]
    curve_ids: list[Any]
    fn: dict[Any, Callable[..., Any]]
    method: str
    name: str


@dataclass
class VulnerabilityMeta:
    """Small container for multiple vulnerability datasets."""

    datasets: dict[str, VulnerabilityDataset]


def get_vulnerability_meta(
    vulnerability: NetcdfReader,
    variables: Sequence[VulnerabilityVariable],
    names: list[str],
) -> VulnerabilityMeta:
    """Obtain the metadata from the vulnerability datasets.

    Parameters
    ----------
    vulnerability : NetcdfReader
        The vulnerability data.
    variables : Sequence[VulnerabilityVariable]
        The settings of the vulnerability datasets (variables).
    names : list[str]
        The names of the vulnerability datasets (variables) to use, these must be
        among the `variables`.

    Returns
    -------
    VulnerabilityMeta
        The vulnerability metadata.
    """
    if isinstance(names, str):
        names = [names]
    settings = {item.name: item for item in variables}
    check_vuln_variables(names, list(settings))
    check_vuln_variables(names, vulnerability.names)

    datasets = {}
    for name in names:
        var = vulnerability.variables[name]

        # Get the method
        method_name = settings[name].method
        check_vuln_method(name, method_name)
        method = import_module(f"{FIAT_METHOD}.{method_name}")

        # Sort out the dimensions
        dims = list(var.dims or ())
        curve_dim = next(
            (item for item in dims if item.startswith(f"{CURVE}_")),
            None,
        )
        if curve_dim is None:
            raise FIATDataError(
                f"No curve dimension ('{CURVE}_*') found for vulnerability \
dataset '{name}'"
            )
        index_dims = [item for item in dims if item != curve_dim]

        # Get the axis types from the settings
        types = settings[name].types or {}
        check_vuln_types_keys(name, list(types.keys()), index_dims)
        check_vuln_types_missing(name, list(types.keys()), index_dims)
        axis_types = [types[dim] for dim in index_dims]
        check_vuln_axis_types(
            name,
            axis_types=axis_types,
            method_axis_types=method.AXIS_TYPES,
            ndatasets=method.NDATASETS,
        )
        axes = {dim: np.asarray(vulnerability.dims[dim][:]) for dim in index_dims}
        for dim, values in axes.items():
            check_vuln_axes(name, dim, values)

        # Order the index axes like the method, curve dimension last
        if len(index_dims) > 1:
            index_dims = [index_dims[axis_types.index(t)] for t in method.AXIS_TYPES]
            axis_types = list(method.AXIS_TYPES)
        # Types are validated by check_vuln_axis_types
        axis_types_out = tuple(str(item) for item in axis_types)
        values = np.moveaxis(
            np.asarray(var.load()),
            [dims.index(dim) for dim in index_dims + [curve_dim]],
            list(range(len(dims))),
        )

        # Set the curve functions
        curve_ids = vulnerability.dims[curve_dim][:].tolist()
        fn = {}
        for idx, curve in enumerate(curve_ids):
            if len(index_dims) == 1:
                fn[curve] = Interp1D(axes[index_dims[0]], values[:, idx])
                continue
            fn[curve] = InterpND(
                [axes[dim] for dim in index_dims],
                values[..., idx],
            )
        var.clear()

        datasets[name] = VulnerabilityDataset(
            axis_types=axis_types_out,
            curve_ids=curve_ids,
            fn=fn,
            method=method_name,
            name=name,
        )

    # Set the metadata
    meta = VulnerabilityMeta(datasets=datasets)

    return meta


def get_method_types(
    vulnerability_meta: VulnerabilityMeta,
) -> list[str]:
    """Return the hazard types needed by the methods of the vulnerability datasets.

    Parameters
    ----------
    vulnerability_meta : VulnerabilityMeta
        The vulnerability metadata.

    Returns
    -------
    list[str]
        The ordered union of the `TYPES` of the methods.
    """
    types: dict[str, None] = {}
    for ds in vulnerability_meta.datasets.values():
        method = import_module(f"{FIAT_METHOD}.{ds.method}")
        types.update(dict.fromkeys(method.TYPES))
    return list(types)


@dataclass
class HazardMeta:
    """Small container for exposure metadata."""

    density: list[float | int]
    ids: list[str]
    indices_run: list[list[int]]
    indices_type: list[list[str]]
    length: int
    rp: list[float]
    types: list[str]


def _hazard_id(value: Any) -> str:
    """Return the identifier of a hazard band as a string (e.g. 2.0 -> '2')."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return str(value)
    if value.is_integer():
        return str(int(value))
    return str(value)


def get_hazard_meta(
    hazard: NetcdfReader,
    variables: Sequence[HazardVariable],
    risk: bool,
    method_types: list[str],
) -> HazardMeta:
    """Obtain some metadata from the hazard data.

    Parameters
    ----------
    hazard : NetcdfReader
        The hazard data.
    variables : Sequence[HazardVariable]
        The settings of the hazard variables (bands), other variables in the hazard
        data are ignored.
    risk : bool
        Whether it is a risk calculation (bands identified by their return period).
    method_types : list[str]
        The hazard types needed by the methods, in order.

    Returns
    -------
    HazardMeta
        The hazard metadata, `indices_run` holding per hazard identifier the band
        indices (of the hazard data) ordered like `types`.
    """
    # Positions of the listed variables in the hazard data
    names = hazard.names
    check_hazard_variables([item.name for item in variables], names)
    positions = [names.index(item.name) for item in variables]

    # Get the types from the settings (indices are positions in the settings)
    types = [item.type for item in variables]
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
        check_hazard_variable_rp([item.name for item in variables if item.rp is None])
        ids, ids_list = check_hazard_identifier(
            [_hazard_id(item.rp) for item in variables],
            indices_type=indices_type,
        )

    # Look at risk specific info
    d = None
    rp = None
    if risk:
        rp = check_hazard_rp(ids)
        d = fn_density(rp)

    # Set the grouped indices, now as indices of the hazard data
    indices_run = [
        [
            positions[indices_type[idx][item.index(idi)]]
            for idx, item in enumerate(ids_list)
        ]
        for idi in ids
    ]
    indices_type = [[positions[idx] for idx in item] for item in indices_type]

    # Fill in the meta
    meta = HazardMeta(
        density=d,
        ids=ids,
        indices_run=indices_run,
        indices_type=indices_type,
        length=len(ids),
        rp=rp,
        types=list(method_types),
    )
    return meta


def _hazard_indices(
    method_name: str,
    hazard_meta: HazardMeta,
) -> list[tuple[int, ...]]:
    """Return per hazard identifier the band indices in the method's type order."""
    method = import_module(f"{FIAT_METHOD}.{method_name}")
    missing = [item for item in method.TYPES if item not in hazard_meta.types]
    if missing:
        raise FIATDataError(
            f"Hazard type(s) {missing} needed by method '{method_name}' not found"
        )
    pos = [hazard_meta.types.index(item) for item in method.TYPES]
    return [tuple(indices[idx] for idx in pos) for indices in hazard_meta.indices_run]


@dataclass
class ExposureGeomData:
    """Small container for exposure geometry data and settings."""

    area_method: str
    data: Any
    impact_types: list[str]
    path: Path
    vulnerability: str
    zonal_method: str

    def __hash__(self):
        return hash(self.data)


@dataclass
class ExposureGeomMeta:
    """Small container for exposure geometry metadata.

    A geometry file is linked to a single vulnerability dataset, so its method, \
curves and hazard band indices (per hazard identifier, ordered like the method's \
`TYPES`) are stored here.
    """

    area_method: str
    fn: dict[Any, Callable[..., Any]]
    hazard_indices: list[tuple[int, ...]]
    indices_ead: dict[str, int]
    indices_impact: dict[str, Any]
    indices_new: list[int]
    indices_spec: list[int]
    indices_total: dict[str, list[int]]
    indices_type: dict[str, Any]
    method: str
    new: list[str]
    new_length: int
    type_length: int
    zonal_method: str


def _geom_curve_ids(
    exposure: ExposureGeomData,
    indices_type: dict[str, Any],
) -> list[Any]:
    """Return the unique curve ids from the curve columns of a geometry file."""
    indices = [f for value in indices_type.values() for f, _ in value]
    ids: dict[Any, None] = {}
    for ft in exposure.data:
        for idx in indices:
            curve_id = ft.get_field(idx)
            if curve_id:
                ids[curve_id] = None
    return list(ids)


def get_exposure_geom_meta(
    exposure: ExposureGeomData,
    run_meta: RunMeta,
    hazard_meta: HazardMeta,
    vulnerability_meta: VulnerabilityMeta,
) -> ExposureGeomMeta:
    """Obtain the run metadata of an exposure geometry file.

    Parameters
    ----------
    exposure : ExposureGeomData
        The exposure geometry data and settings.
    run_meta : RunMeta
        The run metadata.
    hazard_meta : HazardMeta
        The hazard metadata.
    vulnerability_meta : VulnerabilityMeta
        The vulnerability metadata, containing the dataset linked to the file.

    Returns
    -------
    ExposureGeomMeta
        The exposure geometry metadata.
    """
    layer = Path(exposure.path).name
    # Get the linked vulnerability dataset and its method
    check_vuln_variables(
        [exposure.vulnerability],
        list(vulnerability_meta.datasets.keys()),
    )
    ds = vulnerability_meta.datasets[exposure.vulnerability]
    method = import_module(f"{FIAT_METHOD}.{ds.method}")
    if method.NDATASETS > 1:
        raise FIATDataError(
            f"Vulnerability dataset '{ds.name}' of exposure '{layer}' uses method \
'{ds.method}', which combines {method.NDATASETS} datasets; exposure geometries \
are linked to exactly one dataset"
        )

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

    # Check the curve ids against the linked dataset
    for curve_id in _geom_curve_ids(exposure, indices_type):
        check_vuln_curve_ids(
            layer,
            curve_id=curve_id,
            dataset=ds.name,
            available=ds.curve_ids,
        )

    # The length of columns per hazard
    hazard_length = len(method.NEW_COLUMNS)
    type_length = (
        hazard_length + sum([len(item) for item in type_dict.values()]) + len(type_dict)
    )

    ## Names of the new columns
    extra = []
    if run_meta.risk:
        extra = [EAD]
        if len(type_dict) > 1:
            extra = [f"{EAD}_{t}" for t in type_dict]
    new = generate_output_columns(
        method.NEW_COLUMNS,
        type_dict,
        hazard_ids=hazard_meta.ids,
        extra=extra,
    )

    # Indices of colums during calculation
    offset = hazard_length
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

    # Indices of the ead columns (one per impact type)
    indices_ead = {}
    if run_meta.risk:
        start = len(new) - len(extra)
        indices_ead = {t: start + i for i, t in enumerate(type_dict)}

    # Set the indices for the outgoing columns
    indices_new = list(range(len(columns), len(columns) + len(new)))

    # Create the exposure meta struct
    meta = ExposureGeomMeta(
        area_method=exposure.area_method,
        fn=ds.fn,
        hazard_indices=_hazard_indices(ds.method, hazard_meta),
        indices_ead=indices_ead,
        indices_impact=indices_impact,
        indices_new=indices_new,
        indices_spec=indices_spec,
        indices_total=indices_total,
        indices_type=indices_type,
        method=ds.method,
        new=new,
        new_length=len(new),
        type_length=type_length,
        zonal_method=exposure.zonal_method,
    )
    return meta


@dataclass
class GridUnit:
    """Small container for a single grid calculation unit.

    A unit is one call of a method for an exposure layer (or category value
    variable) per hazard identifier.
    """

    curves: tuple[Callable[..., Any], ...] | dict[int, tuple[Callable[..., Any], ...]]
    exp_index: int
    hazard_indices: list[tuple[int, ...]]
    method: str
    out_indices: list[int]
    value_index: int | None = None


@dataclass
class ExposureGridMeta:
    """Small container for exposure grid metadata."""

    index_ead: int | None
    indices_total: list[int]
    nb: int
    new: list[str]
    totals: list[list[int]]
    units: list[GridUnit]


def _as_list(value: str | list[str] | None) -> list[str]:
    """Return a (vulnerability) link as a list."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def _grid_categories(
    exposure: NetcdfReader,
    layer: str,
    value_var: str,
) -> list[Any]:
    """Return the categories from the category coordinate of a value variable."""
    dims = exposure.variables[value_var].dims or ()
    if len(dims) != 1 or dims[0] not in exposure.dims:
        raise FIATDataError(
            f"Category value variable '{value_var}' of categorized layer '{layer}' \
has no single category dimension"
        )
    return np.asarray(exposure.dims[dims[0]][:]).tolist()


def _grid_category_ids(
    layer: str,
    categories: list[Any],
) -> list[int]:
    """Return the categories (zero excluded) as integers."""
    ids = []
    for item in categories:
        try:
            valid = float(item).is_integer()
        except (TypeError, ValueError):
            valid = False
        if not valid:
            raise FIATDataError(
                f"Category '{item}' of exposure layer '{layer}' is not an integer"
            )
        if int(item) != 0:
            ids.append(int(item))
    return ids


def _grid_groups(
    layer: str,
    names: list[str],
    vulnerability_meta: VulnerabilityMeta,
) -> list[tuple[str, list[VulnerabilityDataset]]]:
    """Group the linked datasets of a layer into calculation units.

    Datasets sharing a method that combines several datasets form one group, ordered
    like the method's `AXIS_TYPES`. Every other dataset is a group by itself.
    """
    check_vuln_variables(names, list(vulnerability_meta.datasets.keys()))
    groups: dict[tuple[bool, str], list[VulnerabilityDataset]] = {}
    for name in names:
        ds = vulnerability_meta.datasets[name]
        method = import_module(f"{FIAT_METHOD}.{ds.method}")
        key = (True, ds.method) if method.NDATASETS > 1 else (False, name)
        groups.setdefault(key, []).append(ds)

    out = []
    for group in groups.values():
        method_name = group[0].method
        method = import_module(f"{FIAT_METHOD}.{method_name}")
        check_vuln_grid_method(
            layer,
            method=method_name,
            types=method.TYPES,
            axis_types=method.AXIS_TYPES,
        )
        if method.NDATASETS > 1:
            axis_types = [item.axis_types[0] for item in group]
            check_vuln_group(
                layer,
                method=method_name,
                ndatasets=method.NDATASETS,
                axis_types=axis_types,
                method_axis_types=method.AXIS_TYPES,
            )
            group = [group[axis_types.index(t)] for t in method.AXIS_TYPES]
        out.append((method_name, group))
    return out


def _grid_unit_name(
    name: str,
    groups: list[tuple[str, list[VulnerabilityDataset]]],
    group: list[VulnerabilityDataset],
) -> str:
    """Return the output name of a unit, with its datasets when there are several."""
    if len(groups) == 1:
        return name
    return f"{name}_{'-'.join([ds.name for ds in group])}"


def _grid_layers(
    exposure: NetcdfReader,
    variables: Sequence[ExposureGridVariable],
) -> list[tuple[int, int | None, list[str]]]:
    """Return the calculation layers of the exposure grid with their datasets."""
    names = exposure.names
    settings = {item.name: item for item in variables}
    check_exp_variables(list(settings), names)
    uniform = [item.name for item in variables if item.value is not None]

    # Sort out the categorized layers and their category value variables
    layers_cat = [item for item in variables if item.type == CATEGORIZED]
    cat_values: dict[str, list[str]] = {}
    for item in layers_cat:
        layer = item.name
        values = item.values
        if values is not None:
            check_exp_cat_values(layer, values=values, available=names)
        else:
            values = [var.name for var in exposure if var.has_as_dim(f"{layer}_cat")]
        cat_values[layer] = values
    check_exp_cat_value(cat_values, uniform=uniform)
    check_exp_cat_value_settings(
        cat_values,
        listed=[item.name for item in variables if item.type == VALUES],
    )

    # The default calculation layers
    out: list[tuple[int, int | None, list[str]]] = [
        (names.index(item.name), None, _as_list(item.vulnerability))
        for item in variables
        if item.type == DEFAULT
    ]

    # The categorized layers per category value variable
    for item in layers_cat:
        for value_var in cat_values[item.name]:
            links = _as_list(settings[value_var].vulnerability)
            out.append((names.index(item.name), names.index(value_var), links))
    if not out:
        raise FIATDataError(
            "No exposure layers found, set them as variables of the exposure grid"
        )
    return out


def get_exposure_grid_datasets(
    exposure: NetcdfReader,
    variables: Sequence[ExposureGridVariable],
) -> list[str]:
    """Return the vulnerability datasets linked to the exposure grid.

    Parameters
    ----------
    exposure : NetcdfReader
        The exposure data.
    variables : Sequence[ExposureGridVariable]
        The settings of the exposure variables (layers).

    Returns
    -------
    list[str]
        The unique names of the linked datasets, in order of appearance.
    """
    names: dict[str, None] = {}
    for _, _, links in _grid_layers(exposure, variables):
        names.update(dict.fromkeys(links))
    return list(names)


def get_exposure_grid_meta(
    exposure: NetcdfReader,
    variables: Sequence[ExposureGridVariable],
    run_meta: RunMeta,
    hazard_meta: HazardMeta,
    vulnerability_meta: VulnerabilityMeta,
) -> ExposureGridMeta:
    """Obtain the run plan (calculation units) for the exposure grid.

    Parameters
    ----------
    exposure : NetcdfReader
        The exposure data.
    variables : Sequence[ExposureGridVariable]
        The settings of the exposure variables (layers).
    run_meta : RunMeta
        The run metadata.
    hazard_meta : HazardMeta
        The hazard metadata.
    vulnerability_meta : VulnerabilityMeta
        The vulnerability metadata.

    Returns
    -------
    ExposureGridMeta
        The exposure grid metadata.
    """
    names = exposure.names
    settings = {item.name: item for item in variables}
    layers = _grid_layers(exposure, variables)

    # Set up the units without output indices, together with their names
    units: list[GridUnit] = []
    unit_names: list[str] = []

    for idx, value_index, links in layers:
        layer = names[idx]
        var = exposure[idx]
        groups = _grid_groups(layer, links, vulnerability_meta)

        # Default layer, a single curve id looked up in every linked dataset
        if value_index is None:
            fn = settings[layer].fn_curve
            for _, group in groups:
                for ds in group:
                    check_vuln_curve_ids(
                        layer,
                        curve_id=fn,
                        dataset=ds.name,
                        available=ds.curve_ids,
                    )
            for method_name, group in groups:
                units.append(
                    GridUnit(
                        curves=tuple(ds.fn[fn] for ds in group),
                        exp_index=idx,
                        hazard_indices=_hazard_indices(method_name, hazard_meta),
                        method=method_name,
                        out_indices=[],
                    )
                )
                unit_names.append(_grid_unit_name(layer, groups, group))
            continue

        # Categorized layer, the categories as curve ids per category value variable
        value_var = names[value_index]
        categories = _grid_categories(exposure, layer, value_var)
        # A uniform layer only has its value as category
        if isinstance(var, ConstantVariable):
            check_exp_cat_uniform(
                layer,
                value=var.value,
                value_var=value_var,
                categories=categories,
            )
            categories = [var.value]
        for method_name, group in groups:
            units.append(
                GridUnit(
                    curves={
                        int(cat): tuple(ds.fn[cat] for ds in group)
                        for cat in group[0].curve_ids
                    },
                    exp_index=idx,
                    hazard_indices=_hazard_indices(method_name, hazard_meta),
                    method=method_name,
                    out_indices=[],
                    value_index=value_index,
                )
            )
            unit_names.append(_grid_unit_name(value_var, groups, group))

    # Set the output indices and names
    nunits = len(units)
    length = hazard_meta.length
    for i, unit in enumerate(units):
        unit.out_indices = [i * length + n for n in range(length)]
    new = [f"{name}_{idi}" for name in unit_names for idi in hazard_meta.ids]
    new += [f"{TOTAL}_{idi}" for idi in hazard_meta.ids]
    indices_total = list(range(nunits * length, nunits * length + length))
    totals = [[unit.out_indices[n] for unit in units] for n in range(length)]

    # Set the ead band
    index_ead = None
    if run_meta.risk:
        index_ead = len(new)
        new += [EAD]

    # Set up the meta
    meta = ExposureGridMeta(
        index_ead=index_ead,
        indices_total=indices_total,
        nb=len(new),
        new=new,
        totals=totals,
        units=units,
    )
    return meta
