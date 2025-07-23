"""Utility of the structs."""

import numpy as np
from numpy import ndarray


def convert_to_numpy_dtype(
    dtypes: list,
) -> object:
    """Convert a list of dtypes to a single numpy dtype.

    Parameters
    ----------
    dtypes : list
        List of dtypes

    Returns
    -------
    object
        Dtype object
    """
    dtype_set = set(dtypes)
    if len(dtype_set) != 1:
        dtype = object
    else:
        dtype = np.dtype(dtype_set.pop()).type
    return dtype


def infer_column_types(arr: ndarray) -> list[str]:
    """Infer dtypes per column from a 2D numpy array.

    Parameters
    ----------
    arr : ndarray
        The numpy array

    Returns
    -------
    list[str]
        Dtypes
    """
    column_types = []
    for i in range(arr.shape[1]):
        col = arr[:, i]
        types = set(type(x) for x in col)
        if len(types) == 1:
            column_types.append(types.pop())
        else:
            column_types.append(str)
    return column_types
