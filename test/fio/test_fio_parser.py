import re

import pytest

from fiat.fio.handler import BufferHandler
from fiat.fio.parser import CSVParser


def test_csvparser_default(handler: BufferHandler):
    # Kickstart the parser
    pa = CSVParser(
        handler,
        delimiter=",",
        header=True,
        index=None,  # This is the most default config in general
    )

    # Assert the attributes
    assert pa.index is None
    assert pa.index_col == -1
    assert pa.ncol == 6
    assert pa.nrow == 5
    assert "object_id" in pa.columns  # As the headers are parsed


def test_csvparser_delimiter(handler: BufferHandler):
    # Kickstart the parser
    pa = CSVParser(
        handler,
        delimiter=";",  # This of course makes no sense for this dataset
        header=True,
        index=None,
    )

    # Assert the attributes
    assert pa.index is None
    assert pa.index_col == -1
    assert pa.ncol == 1
    assert pa.nrow == 5
    assert len(pa.columns) == 1  # Of course the same as `ncol`, but good to verify
    assert "object_id,extract_method" in pa.columns[0]  # One big header


def test_csvparser_no_index(handler: BufferHandler):
    # Kickstart the parser
    pa = CSVParser(
        handler,
        delimiter=",",
        header=True,
        index="object_id",
    )

    # Assert the attributes
    assert pa.index == [1, 2, 3, 4, 5]
    assert pa.index_col == 0  # 'object_id' is the first column
    assert pa.ncol == 6
    assert pa.nrow == 5


def test_csvparser_no_header(handler: BufferHandler):
    # Kickstart the parser
    pa = CSVParser(
        handler,
        delimiter=",",
        header=False,
        index=None,
    )

    # Assert the attributes
    assert pa.index is None
    assert pa.index_col == -1
    assert pa.ncol == 6
    assert pa.nrow == 6
    assert pa.columns is None  # No columns were found


def test_csvparser_no_errors(handler: BufferHandler):
    # Index something thats not there
    with pytest.raises(
        ValueError,
        match=r"^Given index column \(some_var\) not found in the columns \(.*\)$",
    ):
        _ = CSVParser(
            handler,
            delimiter=",",
            header=True,
            index="some_var",
        )

    # To check the dtype error a pre-made parser is created
    pa = CSVParser(
        handler,
        delimiter=",",
        header=True,
        index=None,
    )

    pa.meta["dtypes"] = ["int", "str", "int"]  # Length 3 vs 5 existing columns

    with pytest.raises(
        ValueError,
        match=re.escape(
            "Length of dtypes (3) in meta does not \
match the amount of columns in the dataset (6)",
        ),
    ):
        pa.parse_structure(index=None)
