"""Table structures."""

from math import floor, log10

from numpy import arange, column_stack, interp, ndarray

from fiat.fio.handler import BufferHandler
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
        **kwargs,
    ) -> object:
        self.data = data

        # Supercharge with _Table
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
    def from_stream(
        cls,
        data: BufferHandler,
        columns: list | tuple,
        index: list | tuple = None,
        **kwargs,
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
        dtypes = kwargs["dtypes"]
        ncol = kwargs["ncol"]
        index_col = kwargs["index_col"]
        nchar = kwargs["nchar"]
        _pat_multi = regex_pattern(
            kwargs["delimiter"],
            multi=True,
            nchar=nchar,
        )
        with data as h:
            _d = _pat_multi.split(h.read().strip())

        _f = []
        cols = list(range(ncol))

        if kwargs["index_name"] is not None:
            columns.remove(kwargs["index_name"])
            kwargs["ncol"] -= 1

        if index_col >= 0 and index_col in cols:
            if index is not None:
                index = [
                    dtypes[index_col](item)
                    for item in replace_empty(_d[index_col::ncol])
                ]
            cols.remove(index_col)

        for c in cols:
            _f.append([dtypes[c](item) for item in replace_empty(_d[c::ncol])])

        data = column_stack((*_f,))
        return cls(data=data, index=index, columns=columns, **kwargs)

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

        _rnd = abs(floor(log10(delta)))

        _x = tuple(
            arange(min(self.index), max(self.index) + delta / 2, delta)
            .round(_rnd)
            .tolist()
        )

        _x = list(set(_x + self.index))
        _x.sort()

        _f = []

        for c in self.columns:
            _f.append(interp(_x, self.index, self[:, c]).tolist())

        data = column_stack(_f)

        meta.update(
            {
                "ncol": self.meta["ncol"],
                "nrow": len(data),
            }
        )

        if inplace:
            self.__init__(
                data=data,
                index=_x,
                columns=self.columns,
                **meta,
            )
            return None

        return Table(
            data=data,
            index=_x,
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
        if key not in self.headers:
            raise ValueError("")

        if key == self.index_col:
            return

        _pat_multi = regex_pattern(self.delimiter, multi=True, nchar=self.nchar)
        idx = self.header_index[key]
        new_index = [None] * self.handler.size

        with self.handler as h:
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
        self.data = dict(zip(new_index, self.data.values()))
