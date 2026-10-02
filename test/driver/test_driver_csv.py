from pathlib import Path

import numpy as np
import pytest

from fiat.driver.csv import Table, parse_csv
from fiat.driver.handler import BufferHandler, FileBufferHandler
from fiat.open import open_csv


def test_parse_csv_default(file_buffer_handler: FileBufferHandler):
    # Parse with the most default config
    t = parse_csv(file_buffer_handler, delimiter=",", header=True, index=None)

    # Assert the attributes
    assert isinstance(t, Table)
    assert t.ncol == 3
    assert t.nrow == 21
    assert "depth" in t.columns  # Headers parsed, comment lines skipped
    assert t.dtypes == [float, float, float]
    assert t.index[:5] == (0, 1, 2, 3, 4)  # Default range index


def test_parse_csv_delimiter(file_buffer_handler: FileBufferHandler):
    # A delimiter that makes no sense for this dataset
    t = parse_csv(file_buffer_handler, delimiter=";", header=True, index=None)

    # Everything ends up in a single column
    assert t.ncol == 1
    assert t.nrow == 21
    assert "depth,struct_1" in t.columns[0]


def test_parse_csv_dtypes(buffer_handler: BufferHandler):
    # Parse the mixed dtype buffer
    t = parse_csv(buffer_handler, delimiter=",", header=True, index=None)

    # Assert the inferred dtypes
    assert t.ncol == 3
    assert t.nrow == 2
    assert t.dtypes == [str, int, int]
    assert t.data.dtype == object  # Mixed columns fall back to object


def test_parse_csv_index(file_buffer_handler: FileBufferHandler):
    # Promote the 'depth' column to the index
    t = parse_csv(file_buffer_handler, delimiter=",", header=True, index="depth")

    # Assert the attributes
    assert t.index[:5] == (0.0, 0.25, 0.5, 0.75, 1.0)
    assert t.index_name == "depth"
    assert t.columns == ("struct_1", "struct_2")  # Index column removed
    assert t.shape == (21, 2)


def test_parse_csv_no_header(file_buffer_handler: FileBufferHandler):
    # Parse without a header
    t = parse_csv(file_buffer_handler, delimiter=",", header=False, index=None)

    # Assert the attributes
    assert t.ncol == 3
    assert t.nrow == 22  # Header row is counted as data
    assert t.columns == ("col_0", "col_1", "col_2")  # Generated headers
    assert t.dtypes == [str, str, str]  # The header row makes every column a string


def test_parse_csv_errors(file_buffer_handler: FileBufferHandler):
    # Index a column that is not there
    with pytest.raises(
        ValueError,
        match=r"^Given index column \(some_var\) not found in the columns \(.*\)$",
    ):
        _ = parse_csv(file_buffer_handler, delimiter=",", header=True, index="some_var")


def test_parse_csv_mixed(mixed_buffer_handler: BufferHandler):
    # Parse a buffer with mixed column dtypes
    t = parse_csv(mixed_buffer_handler, delimiter=",", header=True)

    # Assert the inferred structure
    assert isinstance(t, Table)
    assert t.columns == ("id", "count", "ratio", "label")
    assert t.dtypes == [str, int, float, str]
    assert t.data.dtype == object  # Mixed columns fall back to object
    assert t.shape == (3, 4)


def test_parse_csv_mixed_values(mixed_buffer_handler: BufferHandler):
    # Parse the mixed buffer
    t = parse_csv(mixed_buffer_handler, delimiter=",", header=True)

    # Assert individual cells, including an empty float cell
    assert t[0, "count"] == 1
    assert t[2, "label"] == "gamma"
    assert np.isnan(t[1, "ratio"])  # Empty cell becomes nan


def test_parse_csv_string_index(mixed_buffer_handler: BufferHandler):
    # Promote the string 'id' column to the index
    t = parse_csv(mixed_buffer_handler, delimiter=",", header=True, index="id")

    # Assert label based access
    assert t.index_name == "id"
    assert t.index == ("row-a", "row-b", "row-c")
    assert t.columns == ("count", "ratio", "label")
    assert t["row-a", "count"] == 1
    assert t["row-c", "ratio"] == 3.25


def test_parse_csv_numeric_no_header(numeric_buffer_handler: BufferHandler):
    # Parse numeric data without a header
    t = parse_csv(numeric_buffer_handler, delimiter=",", header=False)

    # Assert the generated columns and float backing
    assert t.columns == ("col_0", "col_1")
    assert t.dtypes == [int, float]
    assert t.data.dtype == np.float64  # Numeric columns share a float frame
    assert t[0, "col_0"] == 1.0
    assert t[1, "col_1"] == 4.0


def test_open_csv(vulnerability_path: Path):
    # Open a real curve file through the public entry point
    t = open_csv(vulnerability_path, index="depth")

    # Assert it returns the compiled Table
    assert isinstance(t, Table)
    assert t.index_name == "depth"
    assert t.columns == ("struct_1", "struct_2")
    assert t.index[:3] == (0.0, 0.25, 0.5)
    assert t[0.0, "struct_1"] == 0.0


def test_table(table_array: np.ndarray):
    # Set the object
    t = Table(table_array)

    # Assert some simple stuff
    assert t.columns == ("col_0", "col_1")
    assert t.index == (0, 1)
    assert t.index_name == "index"
    assert isinstance(t.data, np.ndarray)
    assert t.dtypes == [np.int64, np.int64]
    assert len(t) == 2


def test_table_general_properties(table_array: np.ndarray):
    # Set the object
    t = Table(table_array)

    # Assert important general properties
    assert t.duplicate_columns is None
    assert t.ncol == 2
    assert t.nrow == 2
    assert t.shape == (2, 2)


def test_table_from_parse(vulnerability_table: Table):
    # Assert the parsed data
    t = vulnerability_table
    assert "depth" in t.columns
    assert t.dtypes == [float, float, float]
    assert t.index[:5] == (0, 1, 2, 3, 4)
    assert t.shape == (21, 3)


def test_table_get(table_array: np.ndarray):
    # Set the object
    t = Table(table_array)

    # Get items like a numpy array
    np.testing.assert_array_equal(t[0, :], np.array([1, 3]))  # First row
    np.testing.assert_array_equal(t[:, "col_0"], np.array([1, 2]))  # Column by name
    assert t[1, "col_1"] == 4  # Single value


def test_table_column_select(table_array: np.ndarray):
    # Set the object
    t = Table(table_array)

    # Select a whole column like a dataframe
    np.testing.assert_array_equal(t["col_1"], np.array([3, 4]))  # By name
    np.testing.assert_array_equal(t[0], np.array([1, 2]))  # By position


def test_table_set_index(table_array: np.ndarray):
    # Set the object
    t = Table(table_array)
    # Current state
    assert t.index == (0, 1)
    assert t.index_name == "index"
    assert t.shape == (2, 2)

    # Set another column as the index
    t.set_index(1)

    # Assert the state
    assert t.index == (3, 4)
    assert t.index_name == "col_1"
    assert t.shape == (2, 1)
