# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True
"""Fast csv parsing into a numpy backed table.

``parse_csv`` scans the raw bytes of a stream in two tight passes over a single
buffer: the first infers the type of every column, the second fills the numpy
frame straight from the bytes with ``strtod``/``strtoll`` (no per cell python
objects). The resulting :py:class:`Table` wraps a 2D :py:class:`numpy.ndarray`
and can be indexed like both a numpy array (``t[row, col]``) and a dataframe
(``t["column"]``). Row labels are kept as a plain sequence; the label lookup is
only built when a label based row access actually needs it, so a default (range)
index costs nothing for large files.
"""

import numpy as np

from libc.math cimport NAN
from libc.stdint cimport int64_t
from libc.stdlib cimport strtod, strtoll

__all__ = ["Table", "parse_csv"]

# Map the inferred rank (2 = int, 1 = float, 0 = str) to the python caster.
_DTYPES = {0: str, 1: float, 2: int}


# Type sniffing
cdef int _classify(const char* b, Py_ssize_t s, Py_ssize_t e):
    """Rank a field: 2 = int, 1 = float (empty counts as nan), 0 = str."""
    cdef Py_ssize_t i = s
    cdef Py_ssize_t mant = 0
    cdef Py_ssize_t exp = 0
    cdef bint dot = False

    # Empty cells are valid floats, later filled with nan.
    if e <= s:
        return 1
    if b[i] == 45:  # a leading '-' is allowed
        i += 1
    # Integer part and optional fraction, needing one digit in total.
    while i < e and 48 <= b[i] <= 57:
        mant += 1
        i += 1
    if i < e and b[i] == 46:  # '.'
        dot = True
        i += 1
        while i < e and 48 <= b[i] <= 57:
            mant += 1
            i += 1
    if mant == 0:
        return 0
    # Optional exponent.
    if i < e and (b[i] == 69 or b[i] == 101):  # 'E'/'e'
        i += 1
        if i < e and (b[i] == 43 or b[i] == 45):  # '+'/'-'
            i += 1
        while i < e and 48 <= b[i] <= 57:
            exp += 1
            i += 1
        if exp == 0:
            return 0
    # Anything left over means it is not a clean number.
    if i != e:
        return 0
    return 1 if dot else 2


# Dtype helpers
cdef bint _is_int_type(object d):
    """Whether a python/numpy type is integer like."""
    return d is int or (isinstance(d, type) and issubclass(d, np.integer))


cdef bint _is_float_type(object d):
    """Whether a python/numpy type is float like."""
    return d is float or (isinstance(d, type) and issubclass(d, np.floating))


cdef int _frame_kind(list dtypes):
    """Pick a backing storage: 1 = int64, 2 = float64, 0 = object."""
    cdef bint all_int = True
    for d in dtypes:
        if _is_int_type(d):
            continue
        all_int = False
        if not _is_float_type(d):
            return 0
    return 1 if all_int else 2


cdef object _kind_dtype(int kind):
    """Translate a storage kind to a numpy dtype."""
    if kind == 1:
        return np.int64
    if kind == 2:
        return np.float64
    return object


cdef list _infer_dtypes(object data):
    """Infer the python type of each column of a 2D array."""
    cdef list dtypes = []
    cdef Py_ssize_t j
    cdef set types

    for j in range(data.shape[1]):
        types = {type(x) for x in data[:, j]}
        dtypes.append(types.pop() if len(types) == 1 else str)
    return dtypes


# Column header housekeeping
cdef list _resolve_columns(list cols):
    """Suffix duplicate headers and name the empty ones."""
    cdef dict seen = {}
    cdef Py_ssize_t idx
    cdef str col

    for idx, col in enumerate(cols):
        if cols.count(col) > 1:
            cols[idx] = f"{col}_{seen.get(col, 0)}"
            seen[col] = seen.get(col, 0) + 1
    return [col if col else f"Unnamed_{idx + 1}" for idx, col in enumerate(cols)]


cdef object _duplicates(list cols):
    """Return the duplicate headers, or None when there are none."""
    cdef list dup = [col for col in set(cols) if cols.count(col) > 1]
    return dup if dup else None


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

    cdef public object data
    cdef public list dtypes
    cdef public object duplicate_columns
    cdef dict _columns
    cdef object _labels  # None marks the default range index
    cdef dict _lookup  # lazily built label -> position map
    cdef str _index_name

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

    # Private methods
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

    cdef Py_ssize_t _row_pos(self, object label) except -1:
        """Translate a row label to its position, building the map on demand."""
        # The default range index maps a label straight onto its position.
        if self._labels is None:
            return label
        if self._lookup is None:
            self._lookup = {lab: pos for pos, lab in enumerate(self._labels)}
        return self._lookup[label]

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

    # Dunder methods
    def __len__(self) -> int:
        return self.data.shape[0]

    def __repr__(self):
        _mem_loc = f"{id(self):#018x}".upper()
        return f"<{self.__class__.__name__} object at {_mem_loc}>"

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

    def __setitem__(self, key, value):
        self.data[key] = value

    # Methods
    def set_index(self, index_col) -> None:
        """Set a column as the row index.

        Parameters
        ----------
        index_col : int | str
            The position or name of the column to use as the index.
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


def parse_csv(handler, delimiter=",", header=True, index=None) -> Table:
    """Parse a csv stream into a :py:class:`Table`.

    Parameters
    ----------
    handler : FileBufferHandler
        The handler of the stream to the file.
    delimiter : str, optional
        The column separating character, e.g. ``','`` or ``';'``.
    header : bool, optional
        Whether the first non comment line holds the column headers.
    index : str, optional
        Name of the column to use as the row index, by default None.

    Returns
    -------
    Table
        The parsed tabular data.
    """
    cdef bytes nchar = handler.nchar
    cdef bytes bdelim = delimiter.encode()
    cdef bytes raw
    cdef bytes stripped
    cdef const char* base
    cdef int delim = bdelim[0]
    cdef int nl = nchar[len(nchar) - 1]
    cdef Py_ssize_t total, ds, n, i, s, fe, col, nrow, k
    cdef Py_ssize_t pos, le, nextpos
    cdef Py_ssize_t ncol = 0
    cdef int r, kind
    cdef list columns = None
    cdef list cols
    cdef list dtypes
    cdef object dup = None
    cdef int[::1] ranks
    cdef double[::1] fout
    cdef int64_t[::1] iout
    cdef object[::1] oout
    cdef object caster

    # Read everything and drop a possible byte order mark.
    handler.stream.seek(0)
    raw = handler.stream.read().lstrip(b"\xef\xbb\xbf")
    total = len(raw)

    # Walk the leading comment lines and the optional header.
    pos = 0
    ds = 0
    while pos < total:
        le = raw.find(nchar, pos)
        if le == -1:
            stripped = raw[pos:total].rstrip(b"\r")
            nextpos = total
        else:
            stripped = raw[pos:le].rstrip(b"\r")
            nextpos = le + len(nchar)
        # Skip empty lines and metadata comments.
        if not stripped or stripped.startswith(b"#"):
            pos = nextpos
            continue
        if header:
            cols = [item.strip().decode("utf-8") for item in stripped.split(bdelim)]
            dup = _duplicates(cols)
            columns = _resolve_columns(cols)
            ncol = len(columns)
            ds = nextpos  # the body starts after the header
        else:
            # Without a header the first line defines the width and is data.
            ncol = stripped.count(bdelim) + 1
            ds = pos
        break

    # Trim trailing newline characters so there is no phantom final row.
    n = total
    while n > ds and (raw[n - 1] == nl or raw[n - 1] == 13 or raw[n - 1] == 10):
        n -= 1

    base = raw

    # Pass 1: infer the type of every column, degrading int -> float -> str.
    ranks = np.full(ncol if ncol else 1, 2, dtype=np.intc)
    nrow = 1 if n > ds else 0
    i = ds
    col = 0
    while i < n:
        s = i
        while i < n and base[i] != delim and base[i] != nl:
            i += 1
        fe = i
        if fe > s and base[fe - 1] == 13:  # strip a '\r' from '\r\n'
            fe -= 1
        r = _classify(base, s, fe)
        if r < ranks[col]:
            ranks[col] = r
        if i < n and base[i] == nl:
            col = 0
            nrow += 1
            i += 1
        elif i < n and base[i] == delim:
            col += 1
            i += 1
        else:
            i += 1

    dtypes = [_DTYPES[ranks[j]] for j in range(ncol)]
    kind = _frame_kind(dtypes)

    # Pass 2: allocate the frame and fill it straight from the raw bytes.
    data = np.empty((nrow, ncol), dtype=_kind_dtype(kind))
    if kind == 1:
        iout = data.reshape(-1)
    elif kind == 2:
        fout = data.reshape(-1)
    else:
        oout = data.reshape(-1)

    i = ds
    col = 0
    k = 0
    while i < n:
        s = i
        while i < n and base[i] != delim and base[i] != nl:
            i += 1
        fe = i
        if fe > s and base[fe - 1] == 13:
            fe -= 1
        if kind == 2:
            fout[k] = NAN if fe <= s else strtod(base + s, NULL)
        elif kind == 1:
            iout[k] = strtoll(base + s, NULL, 10)
        else:
            # The object path keeps each column's own python type.
            caster = dtypes[col]
            if caster is str:
                oout[k] = raw[s:fe].decode("utf-8")
            elif fe <= s:
                oout[k] = NAN
            elif caster is int:
                oout[k] = strtoll(base + s, NULL, 10)
            else:
                oout[k] = strtod(base + s, NULL)
        k += 1
        if i < n and base[i] == nl:
            col = 0
            i += 1
        elif i < n and base[i] == delim:
            col += 1
            i += 1
        else:
            i += 1

    table = Table(data, columns=columns, dtypes=dtypes, duplicate_columns=dup)

    # Optionally promote a column to the row index.
    if index is not None:
        if columns is None or index not in columns:
            raise ValueError(
                f"Given index column ({index}) not found in the columns ({columns})"
            )
        table.set_index(index)
    return table
