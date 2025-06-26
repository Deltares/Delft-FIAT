import numpy as np

from fiat.struct.util import convert_to_numpy_dtype, infer_column_types


def test_convert_to_numpy_dtype_uni():
    # Call the function
    d = convert_to_numpy_dtype([int, int, int])

    # Assert the output
    assert d is np.int64


def test_convert_to_numpy_dtype_mixed():
    # Call the function
    d = convert_to_numpy_dtype([int, str, float])

    # Assert the output
    assert d is object


def test_infer_column_types_uni(table_array: np.ndarray):
    # Call the function
    d = infer_column_types(table_array)

    # Assert the output
    assert d == [np.int64, np.int64]


def test_infer_column_types_mixed():
    # Create a dummy dataset with mixed types
    data = np.array([[1, 2.2, 2], ["foo", 3.3, 3]], dtype=object)

    # Call the function
    d = infer_column_types(data)

    # Assert the output
    assert d == [str, float, int]
