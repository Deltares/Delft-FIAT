import re
from io import BytesIO

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
    assert pa.ncol == 3
    assert pa.nrow == 21
    assert "water depth" in pa.columns  # As the headers are parsed
    assert pa.dtypes == [float, float, float]


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
    assert pa.nrow == 21
    assert len(pa.columns) == 1  # Of course the same as `ncol`, but good to verify
    assert "water depth,struct_1" in pa.columns[0]  # One big header


def test_csvparser_dtypes(handler: BufferHandler):
    # Set a dummy stream
    s = BytesIO()
    s.write(b"#dtypes=str,int,int\nindex,val1,val2\nfp1,1,2\nfp2,3,4\n")
    s.seek(0)
    handler.stream = s
    handler.stream_info()
    # Kickstart the parser
    pa = CSVParser(
        handler,
        delimiter=",",
        header=True,
        index=None,
    )

    # Assert the attributes
    assert pa.ncol == 3
    assert pa.nrow == 2
    assert pa.dtypes == [str, int, int]


def test_csvparser_meta(handler: BufferHandler):
    # Kickstart the parser
    pa = CSVParser(
        handler,
        delimiter=",",
        header=True,
        index="water depth",
    )

    # Assert the dtypes
    assert pa.meta == {"unit": "meter", "method": ["mean", "max"]}
    assert pa.dtypes == [float, float, float]


def test_csvparser_no_index(handler: BufferHandler):
    # Kickstart the parser
    pa = CSVParser(
        handler,
        delimiter=",",
        header=True,
        index="water depth",
    )

    # Assert the attributes
    assert pa.index[:5] == [0.0, 0.25, 0.5, 0.75, 1.0]
    assert pa.index_col == 0  # 'object_id' is the first column
    assert pa.ncol == 3
    assert pa.nrow == 21


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
    assert pa.ncol == 3
    assert pa.nrow == 22
    assert pa.columns is None  # No columns were found
    assert pa.dtypes == [str, str, str]  # Header included which are strings


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
    handler.stream = s

    with pytest.raises(
        ValueError,
        match=re.escape("Metadata should contain one equals sign ('=')"),
    ):
        _ = CSVParser(
            handler,
            delimiter=",",
            header=True,
            index=None,
        )
