import numpy as np

from libc.math cimport NAN
from libc.stdint cimport int64_t
from libc.stdlib cimport strtod, strtoll

from fiat.driver.csv.table cimport Table
from fiat.driver.csv.util cimport _frame_kind, _kind_dtype

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


def parse_csv(handler, delimiter=",", header=True, index=None) -> Table:
    """Parse a CSV stream into a :py:class:`Table`.

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
