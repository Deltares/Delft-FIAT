"""Table structures."""

from math import floor, log10
from typing import Any

from numpy import arange, delete, empty, float64, interp, ndarray

from fiat.fio.handler import BufferHandler
from fiat.fio.parser import CSVParser
from fiat.struct.base import TableBase
from fiat.struct.util import convert_to_numpy_dtype, infer_column_types
from fiat.util import (
    DD_NOT_IMPLEMENTED,
    NOT_IMPLEMENTED,
    regex_pattern,
    replace_empty,
    text_chunk_gen,
)

__all__ = ["Table", "TableLazy"]


class Table(TableBase):
    """Create a struct based on tabular data in a file.

    Parameters
    ----------
    data : ndarray
        The data in numpy.ndarray format.
    index : list | tuple, optional
        The index column from which the values are taken and used to index the rows.
    columns : list | tuple, optional
        The column headers of the table.
        If not supplied, it will be inferred from the file.

    Returns
    -------
    object
        An object containing actively loaded tabular data.
    """

    def __init__(
        self,
        data: ndarray,
        index: list | tuple = None,
        columns: list | tuple = None,
        index_col: int = -1,
        dtypes: list | tuple | None = None,
        **kwargs,
    ):
        # Set the data directly
        self.data: ndarray = data

        # Check for the dtypes
        if dtypes is None:
            dtypes = infer_column_types(data)

        # Supercharge with _Table
        TableBase.__init__(
            self,
            *data.shape,
            dtypes=dtypes,
            index=index,
            columns=columns,
            **kwargs,
        )

        # Set the index
        self.set_index(index_col)

    def __iter__(self):
        raise NotImplementedError(DD_NOT_IMPLEMENTED)

    def __next__(self):
        raise NotImplementedError(DD_NOT_IMPLEMENTED)

    def __getitem__(self, keys):
        keys = list(keys)

        if keys[0] != slice(None):
            keys[0] = self._index[keys[0]]

        if keys[1] != slice(None):
            keys[1] = self._columns[keys[1]]

        return self.data[keys[0], keys[1]]

    def __setitem__(self, key, value):
        self.data[key] = value

    @classmethod
    def from_parser(
        cls,
        parser: CSVParser,
    ):
        """Create the Table from a data steam (file).

        Parameters
        ----------
        data : BufferHandler
            Handler of the steam to a file.
        columns : list | tuple
            Columns (headers) of the file.
        index : list | tuple, optional
            The index column.
        """
        # Set up the pattern for parsing the data over multiple lines
        _pat_multi = regex_pattern(
            parser.delimiter,
            multi=True,
            nchar=parser.data.nchar,
        )
        # Split all the data into separate entries (row + column values)
        with parser.data as h:
            _d = _pat_multi.split(h.read().strip())

        # Determine the dtype of the underlying dataset
        dtype = convert_to_numpy_dtype(parser.dtypes)

        # Create an empty numpy array to set the data in
        data = empty((parser.nrow, parser.ncol), dtype=dtype)

        # Fill the array with the column parsed to their dtype
        for idx in range(parser.ncol):
            data[:, idx] = [
                parser.dtypes[idx](item)
                for item in replace_empty(_d[idx :: parser.ncol])
            ]

        # Return the object
        return cls(
            data=data,
            index=parser.index,
            columns=parser.columns,
            index_col=parser.index_col,
            dtypes=parser.dtypes,
            duplicate_columns=parser.duplicates,
        )

    def set_index(
        self,
        index_col: int | str,
    ):
        """Set the index of the Table to a specific column.

        Parameters
        ----------
        index_col : int | str
            The index or name of column to be set as the index of the Table.
        """
        # Supercharge for check
        index_col = TableBase.set_index(self, index_col)
        if index_col < 0:
            return

        # Remove the necessary data
        index_name = self.columns[index_col]
        _ = self._columns.pop(index_name)
        _ = self.dtypes.pop(index_col)

        # Modify the data and get the index value
        new_index = self.data[:, index_col].tolist()
        self.data = delete(self.data, index_col, 1)

        # Reset the dtype of the array
        dtype = convert_to_numpy_dtype(self.dtypes)
        self.data = self.data.astype(dtype)

        # Set the new variable
        self._ncol -= 1

        # Recall the set index and column methods
        self._set_index(
            new_index,
            name=index_name,
            internal_index=self._index.values(),
        )
        self._set_columns(self.columns)

    def upscale(
        self,
        delta: float,
        inplace: bool = False,
    ):
        """Upscale the data by a smaller delta.

        Parameters
        ----------
        delta : float
            Size of the new interval.
        inplace : bool, optional
            Whether to execute in place, i.e. overwrite the existing data.
            By default True

        """
        # Set the rounding
        rnd = abs(floor(log10(delta)))
        # Set the new index
        x = tuple(
            arange(min(self.index), max(self.index) + delta / 2, delta)
            .round(rnd)
            .tolist()
        )
        x = list(set(x + self.index))
        x.sort()

        # Create a new empty numpy array with dtype float64 as its interpolated data
        data = empty((len(x), self.ncol), dtype=float64)

        # Fill the columns of the array
        for idx, c in enumerate(self.columns):
            data[:, idx] = interp(x, self.index, self[:, c]).tolist()

        # Set it in place
        index_name = self.index_name  # To preserve the index name
        if inplace:
            self.__init__(
                data=data,
                index=x,
                columns=self.columns,
                **self.kwargs,
            )
            self.index_name = index_name
            return None

        # Return a new object
        obj = Table(
            data=data,
            index=x,
            columns=self.columns,
            **self.kwargs,
        )
        obj.index_name = index_name
        return obj


class TableLazy(TableBase):
    """A lazy read of tabular data in a file.

    Requires a datastream as input.

    Parameters
    ----------
    parser : CSVParser
        A parser containing metadata and the stream to the file.
    index : str | tuple, optional
        The index column used as row indices.
    columns : list, optional
        The column headers of the table.

    Returns
    -------
    object
        An object containing a connection via a stream to a file.
    """

    def __init__(
        self,
        parser: CSVParser,
        index: str | tuple = None,
        columns: list = None,
    ):
        # Set the stream as the data
        self.data: BufferHandler = parser.data
        self.delimiter: str = parser.delimiter

        # Get internal indexing
        index_int = [None] * parser.nrow
        _c = 0

        with self.data as h:
            while True:
                index_int[_c] = h.tell()
                _c += 1
                if not h.readline() or _c == parser.nrow:
                    break

        # Set the index and column
        columns = columns or parser.columns
        index = index or parser.index

        # Supercharge with the base table class
        TableBase.__init__(
            self,
            parser.nrow,
            parser.ncol,
            dtypes=parser.dtypes,
            index=index,
            columns=columns,
            internal_index=index_int,
        )

        # Set the index (column)
        if TableBase.set_index(self, parser.index_col) >= 0:
            self.index_name = self.columns[parser.index_col]

    def __iter__(self):
        raise NotImplementedError(DD_NOT_IMPLEMENTED)

    def __next__(self):
        raise NotImplementedError(DD_NOT_IMPLEMENTED)

    def __getitem__(
        self,
        oid: Any,
    ) -> bytes:
        try:
            idx = self._index[oid]
        except Exception:
            return None

        self.data.stream.seek(idx)

        return self.data.stream.readline().strip()

    def _build_lazy(self):
        raise NotImplementedError(NOT_IMPLEMENTED)

    def get(
        self,
        oid: Any,
    ) -> bytes:
        """Get a row from the table based on the index.

        Parameters
        ----------
        oid : Any
            Row identifier.
        """
        return self.__getitem__(oid)

    def set_index(
        self,
        index_col: int | str,
    ):
        """Set the index of the table.

        Parameters
        ----------
        index_col : int | str
            Column header index or name. View available headers via <object>.columns.
        """
        # Supercharge for check
        index_col = TableBase.set_index(self, index_col)
        if index_col < 0:
            return

        # Set up the pattern for parsing the data over multiple lines
        _pat_multi = regex_pattern(self.delimiter, multi=True, nchar=self.data.nchar)
        # Find the index of the index column
        new_index = [None] * self.data.size

        # Go through the data and collect all the index column data
        with self.data as h:
            c = 0
            for _nlines, sd in text_chunk_gen(h, _pat_multi, nchar=self.data.nchar):
                new_index[c:_nlines] = [
                    *map(
                        self.dtypes[index_col],
                        [item.decode() for item in sd[index_col :: self._ncol]],
                    )
                ]
                c += _nlines
            sd = None

        self._set_index(
            new_index,
            name=self.columns[index_col],
            internal_index=self._index.values(),
        )
