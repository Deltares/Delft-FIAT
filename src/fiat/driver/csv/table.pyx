"""The table structure"""

import numpy as np

from fiat.driver.csv.util cimport _frame_kind, _kind_dtype

# Table helpers
cdef list _infer_dtypes(object data):
    """Infer the python type of each column of a 2D array."""
    cdef list dtypes = []
    cdef Py_ssize_t j
    cdef set types

    for j in range(data.shape[1]):
        types = {type(x) for x in data[:, j]}
        dtypes.append(types.pop() if len(types) == 1 else str)
    return dtypes


cdef class Table:
    """A numpy backed table indexable like an array and a dataframe.

    Parameters
    ----------
    data : numpy.ndarray
        The tabular data as a 2D array.
    index : list | tuple, optional
        The row labels. Defaults to a simple range (stored lazily).
    columns : list | tuple, optional
        The column headers. Defaults to ``col_0``, ``col_1``, ...
    dtypes : list, optional
        The python type per column. Inferred from the data when omitted.
    duplicate_columns : list, optional
        The duplicate headers found while parsing, by default None.
    """

    def __init__(
        self,
        object data,
        index=None,
        columns=None,
        dtypes=None,
        duplicate_columns=None,
    ):
        # Set the data and its column types directly.
        self.data = data
        self.dtypes = list(dtypes) if dtypes is not None else _infer_dtypes(data)
        self.duplicate_columns = duplicate_columns
        self._index_name = "index"

        # A range index is left implicit; only real labels are stored.
        self._labels = None if index is None else tuple(index)
        self._lookup = None
        self._set_columns(columns)

    # Dunder methods
    def __getitem__(self, keys):
        # A single key selects a whole column (by name or position).
        if not isinstance(keys, tuple):
            if isinstance(keys, str):
                keys = self._columns[keys]
            return self.data[:, keys]

        # A pair indexes rows then columns, mapping labels to positions.
        row, col = keys
        if row != slice(None):
            row = self._row_pos(row)
        if col != slice(None) and isinstance(col, str):
            col = self._columns[col]
        return self.data[row, col]

    def __len__(self) -> int:
        return self.data.shape[0]

    def __repr__(self):
        _mem_loc = f"{id(self):#018x}".upper()
        return f"<{self.__class__.__name__} object at {_mem_loc}>"

    def __setitem__(self, key, value):
        self.data[key] = value

    # Properties
    @property
    def columns(self) -> tuple:
        """Return the columns."""
        return tuple(self._columns.keys())

    @property
    def index(self) -> tuple:
        """Return the row labels."""
        if self._labels is None:
            return tuple(range(self.data.shape[0]))
        return self._labels

    @property
    def index_name(self) -> str:
        """Return the name of the index."""
        return self._index_name

    @index_name.setter
    def index_name(self, value: str):
        """Set the name of the index."""
        self._index_name = value

    @property
    def ncol(self) -> int:
        """Return the number of columns."""
        return self.data.shape[1]

    @property
    def nrow(self) -> int:
        """Return the number of rows."""
        return self.data.shape[0]

    @property
    def shape(self) -> tuple:
        """Return the shape."""
        return (self.data.shape[0], self.data.shape[1])

    # Private methods
    cdef Py_ssize_t _row_pos(self, object label) except -1:
        """Translate a row label to its position, building the map on demand."""
        # The default range index maps a label straight onto its position.
        if self._labels is None:
            return label
        if self._lookup is None:
            self._lookup = {lab: pos for pos, lab in enumerate(self._labels)}
        return self._lookup[label]

    cdef void _set_columns(self, columns):
        """Set the column lookup, generating headers when absent."""
        if columns is None:
            columns = [f"col_{num}" for num in range(self.data.shape[1])]
        if len(columns) != self.data.shape[1]:
            raise ValueError(
                f"Size of columns ({len(columns)}) not the same \
as the data ({self.data.shape[1]})"
            )
        self._columns = dict(zip(columns, range(len(columns))))

    # Methods
    def set_index(self, index_col) -> None:
        """Set a column as the row index.

        Parameters
        ----------
        index_col : int | str
            The position or name of the column to use as the index.

        Returns
        -------
        None
            The table is updated in place.
        """
        # Resolve the column name to a position.
        if isinstance(index_col, str):
            index_col = self._columns.get(index_col, -1)
        if index_col not in range(self.data.shape[1]):
            raise ValueError(f"Index column index out of range: ({index_col})")

        # Pop the column from the headers and types.
        name = self.columns[index_col]
        columns = [col for col in self.columns if col != name]
        new_index = self.data[:, index_col].tolist()
        self.dtypes.pop(index_col)

        # Drop the column from the data and recast the remaining frame.
        dtype = _kind_dtype(_frame_kind(self.dtypes))
        self.data = np.delete(self.data, index_col, 1).astype(dtype)

        # Reset the lookups with the new index.
        self._set_columns(columns)
        self._labels = tuple(new_index)
        self._lookup = None
        self._index_name = name
