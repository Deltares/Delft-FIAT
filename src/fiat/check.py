"""Checks for the data of FIAT."""

from importlib.util import find_spec
from itertools import chain
from pathlib import Path
from typing import Any

import numpy as np
from pyproj.crs import CRS

from fiat.container import Container
from fiat.error import FIATDataError
from fiat.log import spawn_logger
from fiat.util import FIAT_METHOD, get_crs_repr

logger = spawn_logger(__name__)


## Config
def check_available_values(
    value: Any,
    available: list[Any],
    msg: str,
) -> None:
    """Check whether this settings is available."""
    if value not in available:
        raise FIATDataError(
            f"{msg} value: '{value}' invalid, chose from {available}",
        )


## Text files
def check_duplicate_columns(
    cols: tuple | list,
) -> None:
    """Check for duplicate column headers."""
    if cols is not None:
        msg = f"Duplicate columns were encountered. Wrong column could \
be used. Check input for these columns: {cols}"
        raise FIATDataError(msg)


## GIS
def check_grid_exact(
    haz,
    exp,
) -> bool:
    """Check whether the hazard and exposure grid align."""
    if not check_vs_crs(
        haz.profile.crs,
        exp.profile.crs,
    ):
        msg = f"CRS of hazard data ({get_crs_repr(haz.profile.crs)}) does not \
match the CRS of the exposure data ({get_crs_repr(exp.profile.crs)})"
        logger.warning(msg)
        return False

    gtf1 = [round(_n, 2) for _n in haz.profile.transform]
    gtf2 = [round(_n, 2) for _n in exp.profile.transform]

    if gtf1 != gtf2:
        msg = f"Geotransform of hazard data ({gtf1}) does not match geotransform of \
exposure data ({gtf2})"
        logger.warning(msg)
        return False

    if haz.profile.shape != exp.profile.shape:
        msg = f"Shape of hazard ({haz.profile.shape}) does not match shape of \
exposure data ({exp.profile.shape})"
        logger.warning(msg)
        return False

    return True


def check_internal_crs(
    source_crs: CRS,
    fname: str,
) -> None:
    """Check the internal spatial reference system.

    This also should exist.
    """
    if source_crs is None:
        msg = f"Coordinate reference system is unknown for '{fname}', \
cannot safely continue"
        raise FIATDataError(msg)


def check_geom_extent(
    gm_bounds: tuple | list,
    gr_bounds: tuple | list,
) -> None:
    """Check whether the geometries lie within the bounds of the hazard data."""
    _checks = (
        gm_bounds[0] >= gr_bounds[0],
        gm_bounds[1] >= gr_bounds[1],
        gm_bounds[2] <= gr_bounds[2],
        gm_bounds[3] <= gr_bounds[3],
    )

    if not all(_checks):
        msg = f"Geometry bounds {gm_bounds} exceed hazard bounds {gr_bounds}"
        logger.warning(msg)


def check_vs_crs(
    target_crs: CRS,
    source_crs: CRS,
):
    """Check if the spatial reference systems match."""
    return CRS.from_user_input(target_crs.to_wkt()) == CRS.from_user_input(
        source_crs.to_wkt()
    )


## Input Data
def check_input_data(
    *input: list[str, Any, type],
) -> None:
    """Check if all input data is present."""
    for item in input:
        name, data, dtype = item
        if isinstance(data, Container):
            if len(data) == 0:
                raise ValueError(f"{name} is empty")
            if not all(isinstance(e, dtype) for e in data):
                raise TypeError(f"Wrong type encountered in {name}")
            continue
        if data is None or not isinstance(data, dtype):
            raise TypeError(
                f"{name} is incorrectly set, \
currently of type {data.__class__.__name__}"
            )


## Hazard
def check_hazard_identifier(
    ids: list[str],
    indices_type: list[list[int]],
) -> tuple[list[int]]:
    """Check the identifiers in the hazard data."""
    # Length per
    l = len(indices_type[0])

    ids_list = []
    # Per type check the validity
    for idxs in indices_type:
        single_type = [ids[i] for i in idxs]
        if len(set(single_type)) != l:
            raise FIATDataError(f"Identifiers set incorrectly for type: {single_type}")
        ids_list.append(single_type)

    # Do a check on the total rp
    ids = list(set(chain(*ids_list)))  # What a beauty
    if len(ids) != l:
        raise FIATDataError(f"Identifiers across types do not match total: {ids}")

    return ids_list[0], ids_list


def check_hazard_rp(
    rp: list,
) -> list[float]:
    """Check the typing of the return periods.

    Applies to risk calculations.
    """
    try:
        out = [float(n) for n in rp]
    except BaseException:
        raise FIATDataError(f"Wrong type in return periods: {rp}")
    return out


def check_hazard_subsets(
    sub: dict,
    path: Path,
) -> None:
    """Check whether there are subsets available."""
    if sub is not None:
        keys = ", ".join(list(sub.keys()))
        msg = f"'{path.name}': cannot read this file as there are \
multiple datasets (subsets). Chose one of the following subsets: {keys}"
        raise FIATDataError(msg)


def check_hazard_variable_rp(
    missing: list[str],
) -> None:
    """Check whether all the hazard variables have a return period.

    Applies to risk calculations.

    Parameters
    ----------
    missing : list[str]
        The names of the hazard variables without a return period.
    """
    if missing:
        raise FIATDataError(
            f"Return period (rp) not set for hazard variable(s) {missing}"
        )


def check_hazard_variables(
    names: list[str],
    available: list[str],
) -> None:
    """Check whether the hazard variables are present in the hazard data.

    Parameters
    ----------
    names : list[str]
        The names of the hazard variables from the settings.
    available : list[str]
        The names of the variables in the hazard data.
    """
    missing = [item for item in names if item not in available]
    if missing:
        raise FIATDataError(f"Hazard variable(s) {missing} not found")


def check_hazard_types(
    types: list,
    mandatory_types: list,
) -> list[int]:
    """Check the hazard types in the dataset."""
    check = [item in types for item in mandatory_types]
    if not all(check):
        missing = [item for item, b in zip(mandatory_types, check) if not b]
        msg = f"Missing mandatory hazard types: {missing}"
        raise FIATDataError(msg)

    # Check the count per type
    count = [types.count(item) for item in mandatory_types]
    if len(set(count)) != 1:
        raise FIATDataError(
            f"Different number of datasets per type: {mandatory_types} -> {count}"
        )

    # Set the indices
    indices = [
        [idx for idx, entry in enumerate(types) if entry == item]
        for item in mandatory_types
    ]
    return indices


## Exposure
def check_exp_cat_uniform(
    layer: str,
    value: Any,
    value_var: str,
    categories: list[Any],
) -> None:
    """Check whether the category of a uniform categorized layer is known.

    Parameters
    ----------
    layer : str
        The name of the uniform categorized layer.
    value : Any
        The (constant) category of the layer.
    value_var : str
        The name of the category value variable.
    categories : list
        The categories from the category coordinate of the value variable.
    """
    if value not in categories:
        raise FIATDataError(
            f"Category {value} of uniform categorized layer '{layer}' is not in the \
categories {categories} of category value variable '{value_var}'"
        )


def check_exp_cat_value(
    layers: dict[str, list[str]],
    uniform: list[str],
) -> None:
    """Check the category value variables of the categorized exposure layers.

    Parameters
    ----------
    layers : dict[str, list[str]]
        The category value variables per categorized layer.
    uniform : list[str]
        The names of the uniform (constant value) layers.
    """
    seen: dict[str, str] = {}
    for layer, values in layers.items():
        _uniform = [item for item in values if item in uniform]
        if _uniform:
            raise FIATDataError(
                f"Category value variable(s) {_uniform} of categorized layer \
'{layer}' can't be uniform layers"
            )
        for item in values:
            if item in seen:
                raise FIATDataError(
                    f"Category value variable '{item}' is shared between \
categorized layers '{seen[item]}' and '{layer}'"
                )
            seen[item] = layer


def check_exp_cat_values(
    layer: str,
    values: list[str],
    available: list[str],
) -> None:
    """Check whether the category value variables are in the exposure data.

    Parameters
    ----------
    layer : str
        The name of the categorized layer.
    values : list[str]
        The names of the category value variables.
    available : list[str]
        The names of the variables in the exposure data.
    """
    missing = [item for item in values if item not in available]
    if missing:
        raise FIATDataError(
            f"Category value variable(s) {missing} of categorized layer \
'{layer}' not found in the exposure data"
        )


def check_exp_variables(
    names: list[str],
    available: list[str],
) -> None:
    """Check whether the exposure variables are present in the exposure data.

    Parameters
    ----------
    names : list[str]
        The names of the exposure variables from the settings.
    available : list[str]
        The names of the variables in the exposure data.
    """
    missing = [item for item in names if item not in available]
    if missing:
        raise FIATDataError(f"Exposure variable(s) {missing} not found")


def check_exp_cat_value_settings(
    layers: dict[str, list[str]],
    listed: list[str],
) -> None:
    """Check whether the category value variables are set in the settings.

    Parameters
    ----------
    layers : dict[str, list[str]]
        The category value variables per categorized layer.
    listed : list[str]
        The names of the exposure variables of type 'values' in the settings.
    """
    for layer, values in layers.items():
        missing = [item for item in values if item not in listed]
        if missing:
            raise FIATDataError(
                f"Category value variable(s) {missing} of categorized layer \
'{layer}' not set as variables of type 'values' in the settings"
            )


def check_exp_columns(
    columns: tuple | list,
    mandatory_columns: tuple | list = [],
) -> None:
    """Check the columns of the exposure data."""
    check = [item in columns for item in mandatory_columns]
    if not all(check):
        missing = [item for item, b in zip(mandatory_columns, check) if not b]
        msg = f"Missing mandatory exposure columns: {missing}"
        raise FIATDataError(msg)


def check_exp_derived_types(
    type: str,
    found: tuple | list,
    missing: tuple | list,
) -> None:
    """Check whether columns are available for a certain exposure type."""
    # Error when no columns are found for vulnerability type
    if not found:
        msg = f"For type: '{type}' no matching columns were found for \
fn_{type}_* and max_{type}_* columns."
        raise FIATDataError(msg)

    # Log when combination of fn and max is missing
    if missing:
        logger.warning(
            f"No every vulnerability curve has a corresponding \
maximum value: {missing}"
        )


## Vulnerability
def check_vuln_axes(
    name: str,
    dim: str,
    values: np.ndarray,
) -> None:
    """Check whether an index axis of a vulnerability dataset is strictly increasing.

    Parameters
    ----------
    name : str
        The name of the vulnerability dataset.
    dim : str
        The name of the index dimension.
    values : np.ndarray
        The values of the index dimension.
    """
    if not np.all(np.diff(np.asarray(values, dtype=np.float64)) > 0):
        raise FIATDataError(
            f"Axis '{dim}' of vulnerability dataset '{name}' is not strictly \
increasing"
        )


def check_vuln_axis_types(
    name: str,
    axis_types: list[str | None],
    method_axis_types: list[str],
    ndatasets: int,
) -> None:
    """Check the axis types of a vulnerability dataset against its method.

    Parameters
    ----------
    name : str
        The name of the vulnerability dataset.
    axis_types : list[str | None]
        The axis types of the index dimensions (None when unknown).
    method_axis_types : list[str]
        The axis types expected by the method (`AXIS_TYPES`).
    ndatasets : int
        The number of datasets the method combines (`NDATASETS`).
    """
    if ndatasets > 1:
        valid = len(axis_types) == 1 and axis_types[0] in method_axis_types
        expected = f"one of {method_axis_types}"
    else:
        valid = len(axis_types) == len(method_axis_types) and sorted(
            axis_types, key=str
        ) == sorted(method_axis_types, key=str)
        expected = f"{method_axis_types}"
    if not valid:
        raise FIATDataError(
            f"Axis types {axis_types} of vulnerability dataset '{name}' do not \
match the method, expected {expected}"
        )


def check_vuln_categories(
    layer: str,
    categories: list[Any],
    dataset: str,
    available: list[Any],
) -> None:
    """Check whether the categories of a layer are curve ids of a dataset.

    Parameters
    ----------
    layer : str
        The name of the exposure layer.
    categories : list
        The categories of the layer (category 0 is ignored).
    dataset : str
        The name of the vulnerability dataset.
    available : list
        The curve ids of the vulnerability dataset.
    """
    missing = [item for item in categories if item != 0 and item not in available]
    if missing:
        raise FIATDataError(
            f"Categories {missing} of exposure layer '{layer}' not found in \
vulnerability dataset '{dataset}'"
        )


def check_vuln_curve_ids(
    layer: str,
    curve_id: Any,
    dataset: str,
    available: list[Any],
) -> None:
    """Check whether a curve id is present in a vulnerability dataset.

    Parameters
    ----------
    layer : str
        The name of the exposure layer.
    curve_id : Any
        The curve id.
    dataset : str
        The name of the vulnerability dataset.
    available : list
        The curve ids of the vulnerability dataset.
    """
    if curve_id not in available:
        raise FIATDataError(
            f"Curve id '{curve_id}' of exposure layer '{layer}' not found in \
vulnerability dataset '{dataset}'"
        )


def check_vuln_grid_method(
    layer: str,
    method: str,
    types: list[str],
    axis_types: list[str],
) -> None:
    """Check whether a method can be used for a grid layer.

    The grid calculations do not convert the hazard (`fn_hazard`), so the hazard
    types have to equal the curve axis types.

    Parameters
    ----------
    layer : str
        The name of the exposure layer.
    method : str
        The name of the method.
    types : list[str]
        The hazard types of the method (`TYPES`).
    axis_types : list[str]
        The curve axis types of the method (`AXIS_TYPES`).
    """
    if list(types) != list(axis_types):
        raise FIATDataError(
            f"Method '{method}' of exposure layer '{layer}' needs a hazard \
conversion ({types} -> {axis_types}), not supported for grid calculations"
        )


def check_vuln_group(
    layer: str,
    method: str,
    ndatasets: int,
    axis_types: list[str],
    method_axis_types: list[str],
) -> None:
    """Check a group of vulnerability datasets combined by one method.

    Parameters
    ----------
    layer : str
        The name of the exposure layer.
    method : str
        The name of the method.
    ndatasets : int
        The number of datasets the method combines (`NDATASETS`).
    axis_types : list[str]
        The axis types of the datasets in the group.
    method_axis_types : list[str]
        The axis types expected by the method (`AXIS_TYPES`).
    """
    if len(axis_types) != ndatasets:
        raise FIATDataError(
            f"Exposure layer '{layer}' links {len(axis_types)} dataset(s) with \
method '{method}', number of datasets should be {ndatasets}"
        )
    if len(set(axis_types)) != len(axis_types):
        raise FIATDataError(
            f"Exposure layer '{layer}' links datasets with duplicate axis types \
{axis_types} for method '{method}'"
        )
    if set(axis_types) != set(method_axis_types):
        raise FIATDataError(
            f"Axis types {axis_types} of the datasets linked to exposure layer \
'{layer}' do not match method '{method}', expected {method_axis_types}"
        )


def check_vuln_method(
    name: str,
    method: str | None,
) -> None:
    """Check whether a vulnerability dataset has a known method.

    Parameters
    ----------
    name : str
        The name of the vulnerability dataset.
    method : str | None
        The name of the method.
    """
    if method is None:
        raise FIATDataError(f"Vulnerability dataset '{name}' has no method")
    try:
        spec = find_spec(f"{FIAT_METHOD}.{method}")
    except ModuleNotFoundError:
        spec = None
    if spec is None:
        raise FIATDataError(
            f"Unknown method '{method}' for vulnerability dataset '{name}'"
        )


def check_vuln_types_keys(
    name: str,
    keys: list[str],
    dims: list[str],
) -> None:
    """Check whether the axis type overrides refer to dimensions of a dataset.

    Parameters
    ----------
    name : str
        The name of the vulnerability dataset.
    keys : list[str]
        The dimension names in the types override.
    dims : list[str]
        The index dimensions of the vulnerability dataset.
    """
    missing = [item for item in keys if item not in dims]
    if missing:
        raise FIATDataError(
            f"Types defined for unknown dimension(s) {missing} of vulnerability \
dataset '{name}', chose from {dims}"
        )


def check_vuln_types_missing(
    name: str,
    keys: list[str],
    dims: list[str],
) -> None:
    """Check whether every index dimension of a dataset has an axis type.

    Parameters
    ----------
    name : str
        The name of the vulnerability dataset.
    keys : list[str]
        The dimension names in the types setting.
    dims : list[str]
        The index dimensions of the vulnerability dataset.
    """
    missing = [item for item in dims if item not in keys]
    if missing:
        raise FIATDataError(
            f"No type set for dimension(s) {missing} of vulnerability dataset \
'{name}', set them with 'types' in the variable settings"
        )


def check_vuln_variables(
    names: list[str],
    available: list[str],
) -> None:
    """Check whether the vulnerability datasets are present.

    Parameters
    ----------
    names : list[str]
        The names of the requested vulnerability datasets.
    available : list[str]
        The names of the datasets in the vulnerability data.
    """
    missing = [item for item in names if item not in available]
    if missing:
        raise FIATDataError(
            f"Vulnerability dataset(s) {missing} not found, chose from {available}"
        )
