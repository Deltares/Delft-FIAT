"""Table structures."""

from math import floor, log10

from numpy import arange, delete, empty, interp, ndarray

from fiat.fio.handler import BufferHandler
from fiat.fio.parser import CSVParser
from fiat.struct.base import TableBase
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
        self.data = data

        # Check for the dtypes
        if dtypes is None:
            dtypes = [str] * data.shape[1]

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

    def __eq__(self, other):
        return NotImplemented

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
        _pat_multi = regex_pattern(
            parser.delimiter,
            multi=True,
            nchar=parser.data.nchar,
        )
        with parser.data as h:
            _d = _pat_multi.split(h.read().strip())

        data = empty((parser.nrow, parser.ncol), dtype=object)

        for idx in range(parser.ncol):
            data[:, idx] = [
                parser.dtypes[idx](item)
                for item in replace_empty(_d[idx :: parser.ncol])
            ]

        return cls(
            data=data,
            index=parser.index,
            columns=parser.columns,
            index_col=parser.index_col,
            dtypes=parser.dtypes,
        )

    def set_index(
        self,
        index_col: int,
    ):
        """_summary_.

        Parameters
        ----------
        index_col : int
            _description_
        """
        cols = list(range(len(self.columns)))

        # Check whether the index column index is valid
        if index_col < 0 or index_col not in cols:
            raise ValueError(f"Index column index not present: ({index_col})")

        # Remove the necessary data
        index_name = self.columns[index_col]
        _ = self._columns.pop(index_name)
        _ = self.dtypes.pop(index_col)

        # Modify the data and get the index value
        new_index = self.data[:, index_col].tolist()
        self.data = delete(self.data, 0, index_col)

        # Set the new variables
        self.index_name = index_name
        self._ncol -= 1

        # Recall the set index and column methods
        self._set_index(new_index, self._index.values())
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
        meta = self.meta.copy()

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

        data = empty((len(x), self.ncol), dtype=object)

        for idx, c in enumerate(self.columns):
            data[:, idx] = interp(x, self.index, self[:, c]).tolist()

        if inplace:
            self.__init__(
                data=data,
                index=x,
                columns=self.columns,
                **meta,
            )
            return None

        return Table(
            data=data,
            index=x,
            columns=list(self.columns),
            **meta,
        )


class TableLazy(TableBase):
    """A lazy read of tabular data in a file.

    Requires a datastream as input.

    Parameters
    ----------
    data : BufferHandler
        A stream.
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
        data: BufferHandler,
        index: str | tuple = None,
        columns: list = None,
        **kwargs,
    ) -> object:
        self.data = data

        # Get internal indexing
        index_int = [None] * kwargs["nrow"]
        _c = 0

        with self.data as h:
            while True:
                index_int[_c] = h.tell()
                _c += 1
                if not h.readline() or _c == kwargs["nrow"]:
                    break

        kwargs["_index_int"] = index_int
        del index_int

        TableBase.__init__(
            self,
            index,
            columns,
            **kwargs,
        )

    def __iter__(self):
        raise NotImplementedError(DD_NOT_IMPLEMENTED)

    def __next__(self):
        raise NotImplementedError(DD_NOT_IMPLEMENTED)

    def __getitem__(
        self,
        oid: object,
    ):
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
        oid: str,
    ):
        """Get a row from the table based on the index.

        Parameters
        ----------
        oid : str
            Row identifier.
        """
        return self.__getitem__(oid)

    def set_index(
        self,
        key: str,
    ):
        """Set the index of the table.

        Parameters
        ----------
        key : str
            Column header.
            View available headers via <object>.columns.
        """
        if key not in self.columns:
            raise ValueError("")

        if key == self.index_col:
            return

        _pat_multi = regex_pattern(self.delimiter, multi=True, nchar=self.nchar)
        idx = self.header_index[key]
        new_index = [None] * self.data.size

        with self.data as h:
            c = 0

            for _nlines, sd in text_chunk_gen(h, _pat_multi, nchar=self.nchar):
                new_index[c:_nlines] = [
                    *map(
                        self.dtypes[idx],
                        [item.decode() for item in sd[idx :: self._ncol]],
                    )
                ]
                c += _nlines
            del sd
        self._index = dict(zip(new_index, self.data.values()))
