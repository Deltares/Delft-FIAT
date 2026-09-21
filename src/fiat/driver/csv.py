"""The csv driver."""

from math import floor, log10

from numpy import arange, delete, empty, float64, interp, ndarray

from fiat.driver.base import TableBase
from fiat.driver.handler import FileBufferHandler
from fiat.driver.util import convert_to_numpy_dtype, infer_column_types
from fiat.util import (
    DD_NOT_IMPLEMENTED,
    _dtypes_from_string,
    _dtypes_reversed,
    deter_type,
    find_duplicates,
    regex_pattern,
    replace_empty,
    text_chunk_gen,
)

__all__ = ["CSVParser", "Table"]


class CSVParser:
    """Parse a csv file.

    Parameters
    ----------
    handler : FileBufferHandler
        The handler of the stream to the file.
    delimiter : str
        The delimiter of the textfile, e.g. ',' or ';'
    header : bool
        Whether there is a header or not.
    index : str, optional
        Index of the csv file (row wise), by default None
    """

    def __init__(
        self,
        handler: FileBufferHandler,
        delimiter: str,
        header: bool,
        index: str | None = None,
    ):
        # The internal variables
        self.columns: list | None = None
        self.delimiter: str = delimiter
        self.data: FileBufferHandler = handler
        self.dtypes: list | None = None
        self.duplicates: list | None = None
        self.index: list | None = None
        self.index_col: int = -1
        self.meta: dict = {}
        self.ncol: int = 0
        self.nrow: int = self.data.size

        # Execute the parsing directly
        self.parse_meta(header)
        self.parse_structure(index=index)

    def parse_meta(
        self,
        header: bool,
    ) -> None:
        """Parse the meta data of the csv file.

        Parameters
        ----------
        header : bool
            Whether there is a header or not.
        """
        # Setup the pattern and reset the stream to the beginning
        _pat = regex_pattern(self.delimiter)
        self.data.stream.seek(0)

        while True:
            # Loop through the lines to discover meta data
            self.nrow -= 1
            cur_pos = self.data.stream.tell()
            line = self.data.stream.readline().decode("utf-8-sig")

            # Line starting with a number sign is demeed metatdata
            if line.startswith("#"):
                t = line.strip().split("=")
                if len(t) != 2:
                    raise ValueError("Metadata should contain one equals sign ('=')")
                entry, value = t
                entry = entry.strip().replace("#", "").lower()
                value = value.strip()
                if len(value.split(self.delimiter)) > 1:
                    value = [item.strip() for item in value.split(self.delimiter)]
                self.meta[entry] = value
                continue

            # After the metadata, the header should be encountered
            # However when not defined the first line is split to determine
            # The amount of columns
            if not header:
                self.columns = None
                self.ncol = len(_pat.split(line.encode("utf-8-sig")))
                self.data.stream.seek(cur_pos)
                self.nrow += 1
                break

            # Otherwise the columns parsed directly from this line
            self.columns = [item.strip() for item in line.split(self.delimiter)]
            self.duplicates = find_duplicates(self.columns)
            self.resolve_column_headers()
            self.ncol = len(self.columns)
            break

        # Skip the lines where metadata is located
        self.data.skip = self.data.stream.tell()

    def parse_structure(
        self,
        index: str | None = None,
    ) -> None:
        """Parse the csv file to create the structure.

        Parameters
        ----------
        index : str, optional
            Index of the csv file.
        """
        # Set up the pattern and the vars for pulling apart the data
        get_index = False
        get_dtypes = True
        _pat_multi = regex_pattern(self.delimiter, multi=True, nchar=self.data.nchar)

        # Check if the index has been provided
        if index is not None and self.columns is not None:
            if index not in self.columns:
                raise ValueError(f"Given index column ({index}) not found \
in the columns ({self.columns})")
            idcol = self.columns.index(index)
            self.index_col = idcol
            index_list = []
            get_index = True

        # Check if dtypes had been present in the metadata
        if "dtypes" in self.meta:
            dtypes = self.meta.pop("dtypes")
            if len(dtypes) != self.ncol:
                raise ValueError(f"Length of dtypes ({len(dtypes)}) in meta does not \
match the amount of columns in the dataset ({len(self.columns)})")

            dtypes = [_dtypes_from_string[item] for item in dtypes]

            self.dtypes = dtypes
            dtypes = None
            get_dtypes = False

        # Pull apart the data to either determine the dtypes and/ or the index
        if get_dtypes or get_index:
            if get_dtypes:
                dtypes = [0] * self.ncol
            with self.data as _h:
                for _nlines, sd in text_chunk_gen(
                    _h, pattern=_pat_multi, nchar=self.data.nchar
                ):
                    if get_dtypes:
                        for idx in range(self.ncol):
                            dtypes[idx] = max(
                                deter_type(b"\n".join(sd[idx :: self.ncol]), _nlines),
                                dtypes[idx],
                            )
                    if get_index:
                        index_list += sd[idcol :: self.ncol]
                    del sd

                if get_dtypes:
                    self.dtypes = [_dtypes_reversed[item] for item in dtypes]
                if get_index:
                    func = self.dtypes[idcol]
                    self.index = [func(item.decode()) for item in index_list]

    def resolve_column_headers(self) -> None:
        """Resolve the column headers."""
        cols = self.columns
        dup = self.duplicates
        if dup is None:
            dup = []
        # Solve duplicate values first
        count = dict(zip(dup, [0] * len(dup)))
        for idx, item in enumerate(cols):
            if item in dup:
                cols[idx] += f"_{count[item]}"
                count[item] += 1

        # Solve unnamed column headers
        cols = [col if col else f"Unnamed_{idx+1}" for idx, col in enumerate(cols)]
        self.columns = cols


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
        data : FileBufferHandler
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
    ) -> None:
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
