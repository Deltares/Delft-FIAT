"""The FIAT model utilities."""

import math
from itertools import product
from typing import Generator

GEOM_DEFAULT_CHUNK = 50000


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
            yield (*cur, *coord)
            cur[s1_idx] += coord[s1_idx]
        cur[1 - s1_idx] += coord[1 - s1_idx]
        cur[s1_idx] = 0


def create_2d_windows(
    shape: tuple,
    origin: tuple,
    window_size: tuple,
) -> Generator[tuple[slice, slice], None, None]:
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
        Tuple containing the upperleft y and x corner and the height and width
    """
    oy, ox = origin
    y, x = shape
    lu = tuple(
        product(
            range(ox, ox + x, window_size[1]),
            range(oy, oy + y, window_size[0]),
        ),
    )
    for l, u in lu:
        h = min(window_size[0], oy + y - u)
        w = min(window_size[1], ox + x - l)
        yield (
            slice(u, u + h),
            slice(l, l + w),
        )
