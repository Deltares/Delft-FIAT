import re
from io import BytesIO

import pytest

from fiat.fio.handler import BufferHandler, FileBufferHandler
from fiat.fio.parser import CSVParser


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
    assert "water depth" in pa.columns  # As the headers are parsed
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
    assert "water depth,struct_1" in pa.columns[0]  # One big header


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
        index="water depth",
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
        index="water depth",
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


def test_csvparser_no_errors(file_buffer_handler: FileBufferHandler):
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
