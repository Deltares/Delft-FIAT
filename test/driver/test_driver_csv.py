import re
from io import BytesIO

import numpy as np
import pytest

from fiat.driver.csv import CSVParser, Table
from fiat.driver.handler import BufferHandler, FileBufferHandler


def test_csvparser_default(file_buffer_handler: FileBufferHandler):
    # Kickstart the parser
    pa = CSVParser(
        file_buffer_handler,
        delimiter=",",
        header=True,
        index=None,  # This is the most default config in general
    )

    # Assert the attributes
    assert pa.index is None
    assert pa.index_col == -1
    assert pa.ncol == 3
    assert pa.nrow == 21
    assert "depth" in pa.columns  # As the headers are parsed
    assert pa.dtypes == [float, float, float]


def test_csvparser_delimiter(file_buffer_handler: FileBufferHandler):
    # Kickstart the parser
    pa = CSVParser(
        file_buffer_handler,
        delimiter=";",  # This of course makes no sense for this dataset
        header=True,
        index=None,
    )

    # Assert the attributes
    assert pa.index is None
    assert pa.index_col == -1
    assert pa.ncol == 1
    assert pa.nrow == 21
    assert len(pa.columns) == 1  # Of course the same as `ncol`, but good to verify
    assert "depth,struct_1" in pa.columns[0]  # One big header


def test_csvparser_dtypes(buffer_handler: BufferHandler):
    # Kickstart the parser
    pa = CSVParser(
        buffer_handler,
        delimiter=",",
        header=True,
        index=None,
    )

    # Assert the attributes
    assert pa.ncol == 3
    assert pa.nrow == 2
    assert pa.dtypes == [str, int, int]


def test_csvparser_meta(file_buffer_handler: FileBufferHandler):
    # Kickstart the parser
    pa = CSVParser(
        file_buffer_handler,
        delimiter=",",
        header=True,
        index="depth",
    )

    # Assert the dtypes
    assert pa.meta == {"unit": "meter", "method": ["mean", "max"]}
    assert pa.dtypes == [float, float, float]


def test_csvparser_no_index(file_buffer_handler: FileBufferHandler):
    # Kickstart the parser
    pa = CSVParser(
        file_buffer_handler,
        delimiter=",",
        header=True,
        index="depth",
    )

    # Assert the attributes
    assert pa.index[:5] == [0.0, 0.25, 0.5, 0.75, 1.0]
    assert pa.index_col == 0  # 'object_id' is the first column
    assert pa.ncol == 3
    assert pa.nrow == 21


def test_csvparser_no_header(file_buffer_handler: FileBufferHandler):
    # Kickstart the parser
    pa = CSVParser(
        file_buffer_handler,
        delimiter=",",
        header=False,
        index=None,
    )

    # Assert the attributes
    assert pa.index is None
    assert pa.index_col == -1
    assert pa.ncol == 3
    assert pa.nrow == 22
    assert pa.columns is None  # No columns were found
    assert pa.dtypes == [str, str, str]  # Header included which are strings


def test_csvparser_errors(file_buffer_handler: FileBufferHandler):
    # Index something thats not there
    with pytest.raises(
        ValueError,
        match=r"^Given index column \(some_var\) not found in the columns \(.*\)$",
    ):
        _ = CSVParser(
            file_buffer_handler,
            delimiter=",",
            header=True,
            index="some_var",
        )

    # To check the dtype error a pre-made parser is created
    pa = CSVParser(
        file_buffer_handler,
        delimiter=",",
        header=True,
        index=None,
    )

    pa.meta["dtypes"] = ["int", "str", "int", "float"]  # Length 4 vs 3 existing columns

    with pytest.raises(
        ValueError,
        match=re.escape(
            "Length of dtypes (4) in meta does not \
match the amount of columns in the dataset (3)",
        ),
    ):
        pa.parse_structure(index=None)

    # To check for the metadata error
    s = BytesIO()
    s.write(b"#foo,bar")
    file_buffer_handler.stream = s

    with pytest.raises(
        ValueError,
        match=re.escape("Metadata should contain one equals sign ('=')"),
    ):
        _ = CSVParser(
            file_buffer_handler,
            delimiter=",",
            header=True,
            index=None,
        )


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

    # Assert  important general properties
    assert t.duplicate_columns is None
    assert t.kwargs == {}
    assert t.ncol == 2
    assert t.nrow == 2
    assert t.shape == (2, 2)


def test_table_from_parser(vulnerability_parsed: CSVParser):
    # Setup the object from class method
    t = Table.from_parser(vulnerability_parsed)

    # Assert the data
    assert "depth" in t.columns
    assert t.dtypes == [float, float, float]
    assert t.index[:5] == (0, 1, 2, 3, 4)
    assert t.kwargs == {"duplicate_columns": None}
    assert t.shape == (21, 3)


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
