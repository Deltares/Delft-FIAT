"""The FIAT model utilities."""

import math
from itertools import product
from typing import Callable, Generator

import numpy as np
from scipy.interpolate import make_interp_spline

from fiat.check import check_hazard_identifier, check_hazard_rp, check_hazard_types
from fiat.fio import GridIO
from fiat.method.ead import fn_density
from fiat.struct import Table
from fiat.struct.container import HazardMeta, VulnerabilityMeta
from fiat.typing import MethodsProtocol

GEOM_DEFAULT_CHUNK = 50000
GRID_PREFER = {
    False: "hazard",
    True: "exposure",
}


def create_1d_chunks(
    length: int,
    parts: int,
) -> tuple:
    """Create chunks for 1d vector data."""
    part = math.ceil(
        length / parts,
    )
    series = list(
        range(0, length, part),
    ) + [length]
    _series = series.copy()
    _series.remove(_series[0])
    series = [_i + 1 for _i in series]

    chunks = tuple(
        zip(series[:-1], _series),
    )

    return chunks


def create_2d_chunks(
    shape: tuple[int],
    parts: int,
):
    """Create chunks for 2d vector data."""
    x, y = shape
    number = x * y
    ratio = y / x
    per_chunk = math.ceil(number / parts)
    res = round(math.sqrt(per_chunk / ratio))

    yield from create_2d_windows(
        shape=shape,
        origin=(0, 0),
        window=(res, round(res * ratio)),
    )


def create_2d_windows(
    shape: tuple,
    origin: tuple,
    window: tuple,
) -> Generator:
    """Create chunk windows from a grid.

    Parameters
    ----------
    shape : tuple
        Shape of the grid.
    origin : tuple
        The origin (array-wise) of the grid.
    window : tuple
        The window size.

    Returns
    -------
    tuple
        Tuple containing the upperleft x and y corner and the width and height
    """
    ox, oy = origin
    x, y = shape
    lu = tuple(
        product(
            range(ox, x, window[0]),
            range(oy, y, window[1]),
        ),
    )
    for l, u in lu:
        w = min(window[0], x - l)
        h = min(window[1], y - u)
        yield (
            l,
            u,
            w,
            h,
        )


def get_band_names(
    ds: GridIO,
) -> list:
    """Determine the names of the bands.

    If the bands do not have any names of themselves,
    they will be set to a default.
    """
    names = []
    for idx, band in enumerate(ds):
        name = band.name
        names.append(name or f"band{idx+1}")

    return names


def get_hazard_meta(
    hazard: GridIO,
    risk: bool,
    method: MethodsProtocol,
) -> HazardMeta:
    """Obtain some metadata from the hazard data."""
    # Get the types from the metadata
    types = [band.get_meta("type") for band in hazard]
    # Check the typing
    indices_type = check_hazard_types(
        types,
        method.TYPES,
    )

    # Get the identifiers:
    identifier = None if not risk else "rp"
    ids = [str(idx + 1) for idx, _ in enumerate(indices_type[0])]
    ids_list = [ids] * len(indices_type)

    # If identifier is not None
    if identifier is not None:
        ids, ids_list = check_hazard_identifier(
            [band.get_meta(identifier) for band in hazard],
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
        risk=risk,
        type=method.NAME,
        type_length=len(method.TYPES),
    )
    return meta


def get_vulnerability_meta(
    vulnerability: Table,
) -> VulnerabilityMeta:
    """Obtain some metadata from the vulnerability data."""
    imin = min(vulnerability.index)
    imax = max(vulnerability.index)
    fn_list = vulnerability.columns
    fn = {
        item: make_interp_spline(vulnerability.index, vulnerability[:, item], k=1)
        for item in fn_list
    }
    meta = VulnerabilityMeta(
        fn=fn,
        fn_list=fn_list,
        min=imin,
        max=imax,
    )
    return meta


def vectorize_function(
    fn: Callable,
    skip: int,
    dtype: type = np.float32,
) -> Callable:
    """Vectorize a function simply."""
    na = fn.__code__.co_argcount
    excluced = set(fn.__code__.co_varnames[skip:na])
    fn_vec = np.vectorize(fn, otypes=[dtype], excluded=excluced)
    return fn_vec
