import numpy as np

from fiat.fio.handler import BufferHandler
from fiat.fio.parser import CSVParser
from fiat.struct.table import Table, TableLazy


def test_table(table_array: np.ndarray):
    # Set the object
    t = Table(table_array)

    # Assert some simple stuff
    assert t.columns == ("col_0", "col_1")
    assert t.index == (0, 1)
    assert t.index_name == "index"
    assert isinstance(t.data, np.ndarray)
    assert t.dtypes == [np.int64, np.int64]


def test_table_general_properties(table_array: np.ndarray):
    # Set the object
    t = Table(table_array)

    # Assert  important general properties
    assert t.duplicate_columns is None
    assert t.kwargs == {}
    assert t.ncol == 2
    assert t.nrow == 2
    assert t.shape == (2, 2)


def test_table_from_parser(exposure_data_parsed: CSVParser):
    # Setup the object from class method
    t = Table.from_parser(exposure_data_parsed)

    # Assert the data
    assert "object_id" in t.columns
    assert t.dtypes == [int, str, int, int, str, int]
    assert t.index == (0, 1, 2, 3, 4)
    assert t.kwargs == {"duplicate_columns": None}
    assert t.shape == (5, 6)


def test_table_get(table_array: np.ndarray):
    # Set the object
    t = Table(table_array)

    # Get items
    d = t[0, :]  # Get first row
    # Assert the output
    np.testing.assert_array_equal(d, np.array([1, 3]))

    d = t[:, "col_0"]  # Get first column
    # Assert the output
    np.testing.assert_array_equal(d, np.array([1, 2]))

    d = t[1, "col_1"]  # single value
    # Assert the output
    assert d == 4


def test_table_set_index(table_array: np.ndarray):
    # Set the object
    t = Table(table_array)
    # Current state
    assert t.index == (0, 1)
    assert t.index_name == "index"
    assert t.shape == (2, 2)

    # Set other columns as the index
    t.set_index(1)

    # Assert the state
    assert t.index == (3, 4)
    assert t.index_name == "col_1"
    assert t.shape == (2, 1)


def test_table_upscale(table_array: np.ndarray):
    # Set the object
    t = Table(table_array)
    # Current state
    assert t.index == (0, 1)
    assert t.shape == (2, 2)

    # Upscale the data
    new = t.upscale(0.5)

    # Assert the state
    assert new.index == (0, 0.5, 1)
    assert new.shape == (3, 2)

    # Do it inplace
    t.upscale(0.5, inplace=True)

    # Assert the state
    assert t.index == (0, 0.5, 1)
    assert t.shape == (3, 2)


def test_tablelazy(exposure_data_parsed: CSVParser):
    # Set the object
    t = TableLazy(exposure_data_parsed)

    # Assert some simple stuff
    assert "object_id" in t.columns
    assert isinstance(t.data, BufferHandler)
    assert t.dtypes == [int, str, int, int, str, int]
    assert t.index == (0, 1, 2, 3, 4)
    assert t.index_name == "index"


def test_tablelazy_general_properties(exposure_data_parsed: CSVParser):
    # Set the object
    t = TableLazy(exposure_data_parsed)

    # Assert  important general properties
    assert t.duplicate_columns is None
    assert t.kwargs == {}
    assert t.ncol == 6
    assert t.nrow == 5
    assert t.shape == (5, 6)


def test_tablelazy_get(exposure_data_parsed: CSVParser):
    # Set the object
    t = TableLazy(exposure_data_parsed)

    # Get a row by direct indexing
    row = t[1]
    # Assert the output
    assert isinstance(row, bytes)
    assert row.startswith(b"2,area")

    # Call the methods
    row = t.get(1)
    # Assert the output
    assert isinstance(row, bytes)
    assert row.startswith(b"2,area")


def test_tablelazy_set_index(exposure_data_parsed: CSVParser):
    # Set the object
    t = TableLazy(exposure_data_parsed)
    # Assert the current state
    assert t.index == (0, 1, 2, 3, 4)
    assert t.index_name == "index"

    # Set the index to a column
    t.set_index(0)

    # Assert the state
    assert t.index == (1, 2, 3, 4, 5)
    assert t.index_name == "object_id"

    # If not found, do nothing
    t.set_index(-1)
    assert t.index_name == "object_id"  # still
