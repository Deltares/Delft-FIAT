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
    """Create chunks for 1d vector data.

    Parameters
    ----------
    length : int
        Length of the series.
    parts : int
        Number of parts in which to divide the series.

    Returns
    -------
    tuple
        A tuple containing tuples with start and stop indices.
    """
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
) -> Generator[tuple, None, None]:
    """Create rectangular chunks roughly equal in number of cells.

    Parameters
    ----------
    shape : tuple[int]
        The shape of the origin grid.
    parts : int
        The number of parts in which the grid (shape) should be divided.

    Yields
    ------
    Generator[tuple]
        A generator of window tuples.
        These tuple are defined as: (x_origin, y_origin, width, height).
    """
    # Set up the base numbers for determining the chunks
    s1_idx = shape.index(max(shape))
    ratio = shape[s1_idx] / shape[1 - s1_idx]
    base = math.sqrt(parts / ratio)
    # Set initial values for the sides
    s1 = min(parts, round(base * ratio), shape[s1_idx])  # Long side
    s2 = max(min(round(base), shape[1 - s1_idx]), 1)  # Short side
    # Append to the long side if it's still off per column/ row
    number = [s1] * s2
    diff = parts - s1 * s2
    if diff != 0:
        sign = int(diff / abs(diff))
        for idx in range(0, abs(diff), abs(sign)):
            number[idx % s2] = min(number[idx % s2] + sign, shape[s1_idx])

    # Larger side division per short side element
    long_side = []
    for item in number:
        elem = [shape[s1_idx] // item for _ in range(item)]
        for idx in range(shape[s1_idx] % item):
            elem[idx] += 1
        long_side.append(elem)

    # Sorter side division
    short_div = [shape[1 - s1_idx] * item / sum(number) for item in number]
    left_over = [item - math.floor(item) for item in short_div]
    short_side = [math.floor(item) for item in short_div]
    while sum(short_side) != shape[1 - s1_idx]:
        idx = left_over.index(max(left_over))
        short_side[idx] += 1
        left_over[idx] = 0
    short_side = [[item] for item in short_side]

    # Add the divisions to a list representing the shape indices
    setup = [None, None]
    setup[s1_idx] = long_side
    setup[1 - s1_idx] = short_side

    # Yield the windows starting of course with an origin of 0,0
    cur = [0, 0]
    for row in zip(*setup):
        for coord in product(*row):
            yield (*cur, coord[1], coord[0])
            cur[1 - s1_idx] += coord[s1_idx]
        cur[s1_idx] += coord[1 - s1_idx]
        cur[1 - s1_idx] = 0


def create_2d_windows(
    shape: tuple,
    origin: tuple,
    window: tuple,
) -> Generator[tuple, None, None]:
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
            range(ox, ox + x, window[1]),
            range(oy, oy + y, window[0]),
        ),
    )
    for l, u in lu:
        w = min(window[1], ox + x - l)
        h = min(window[0], oy + y - u)
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
