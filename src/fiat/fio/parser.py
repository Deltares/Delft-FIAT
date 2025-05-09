"""The csv parser."""

from fiat.fio.handler import BufferHandler
from fiat.util import (
    _dtypes_from_string,
    _dtypes_reversed,
    deter_type,
    find_duplicates,
    regex_pattern,
    text_chunk_gen,
)


class CSVParser:
    """Parse a csv file.

    Parameters
    ----------
    handler : BufferHandler

    delimiter : str
        The delimiter of the textfile, e.g. ',' or ';'
    header : bool
        Whether there is a header or not.
    index : str, optional
        Index of the csv file (row wise), by default None
    """

    def __init__(
        self,
        handler: BufferHandler,
        delimiter: str,
        header: bool,
        index: str = None,
    ):
        self.delimiter = delimiter
        self.data = handler
        self.meta = {}
        self.meta["index_col"] = -1
        self.meta["index_name"] = None
        self.meta["delimiter"] = delimiter
        self.meta["dup_cols"] = None
        self.meta["nchar"] = self.data.nchar
        self.index = None
        self.columns = None
        self._nrow = self.data.size
        self._ncol = 0

        self.parse_meta(header)
        self.parse_structure(index=index)

    def parse_meta(
        self,
        header: bool,
    ):
        """Parse the meta data of the csv file.

        Parameters
        ----------
        header : bool
            Whether there is a header or not.
        """
        _pat = regex_pattern(self.delimiter)
        self.data.stream.seek(0)

        while True:
            self._nrow -= 1
            cur_pos = self.data.stream.tell()
            line = self.data.stream.readline().decode("utf-8-sig")

            if line.startswith("#"):
                t = line.strip().split("=")
                if len(t) == 1:
                    tl = t[0].split(":")
                    if len(tl) > 1:
                        lst = tl[1].split(self.delimiter)
                        _entry = tl[0].strip().replace("#", "").lower()
                        _val = [item.strip() for item in lst]
                        self.meta[_entry] = _val
                    else:
                        lst = t[0].split(self.delimiter)
                        _entry = lst[0].strip().replace("#", "").lower()
                        _val = [item.strip() for item in lst[1:]]
                        self.meta[_entry] = _val
                        # raise ValueError("Supplied metadata in unknown format..")
                else:
                    key, item = t
                    self.meta[key.strip().replace("#", "").lower()] = item.strip()
                continue

            if not header:
                self.columns = None
                self._ncol = len(_pat.split(line.encode("utf-8-sig")))
                self.data.stream.seek(cur_pos)
                self._nrow += 1
                break

            self.columns = [item.strip() for item in line.split(self.delimiter)]
            self.meta["dup_cols"] = find_duplicates(self.columns)
            self.resolve_column_headers()
            self._ncol = len(self.columns)
            break

        self.data.skip = self.data.stream.tell()
        self.meta["ncol"] = self._ncol
        self.meta["nrow"] = self._nrow

    def parse_structure(
        self,
        index: str,
    ):
        """Parse the csv file to create the structure.

        Parameters
        ----------
        index : str
            Index of the csv file.
        """
        _get_index = False
        _get_dtypes = True
        _pat_multi = regex_pattern(self.delimiter, multi=True, nchar=self.data.nchar)

        if index is not None:
            try:
                idcol = self.columns.index(index)
            except Exception:
                idcol = 0
            self.meta["index_col"] = idcol
            self.meta["index_name"] = self.columns[idcol]
            _index = []
            _get_index = True

        if "dtypes" in self.meta:
            _dtypes = self.meta["dtypes"]
            if len(_dtypes) != self._ncol:
                raise ValueError("")

            _dtypes = [_dtypes_from_string[item] for item in _dtypes]

            self.meta["dtypes"] = _dtypes
            _dtypes = None
            _get_dtypes = False

        if _get_dtypes or _get_index:
            if _get_dtypes:
                _dtypes = [0] * self._ncol
            with self.data as _h:
                for _nlines, sd in text_chunk_gen(
                    _h, pattern=_pat_multi, nchar=self.data.nchar
                ):
                    if _get_dtypes:
                        for idx in range(self._ncol):
                            _dtypes[idx] = max(
                                deter_type(b"\n".join(sd[idx :: self._ncol]), _nlines),
                                _dtypes[idx],
                            )
                    if _get_index:
                        _index += sd[idcol :: self._ncol]
                    del sd

                if _get_dtypes:
                    self.meta["dtypes"] = [_dtypes_reversed[item] for item in _dtypes]
                if _get_index:
                    func = self.meta["dtypes"][idcol]
                    self.index = [func(item.decode()) for item in _index]

    def resolve_column_headers(self):
        """Resolve the column headers."""
        _cols = self.columns
        dup = self.meta["dup_cols"]
        if dup is None:
            dup = []
        # Solve duplicate values first
        count = dict(zip(dup, [0] * len(dup)))
        for idx, item in enumerate(_cols):
            if item in dup:
                _cols[idx] += f"_{count[item]}"
                count[item] += 1

        # Solve unnamed column headers
        _cols = [_col if _col else f"Unnamed_{_i+1}" for _i, _col in enumerate(_cols)]
        self.columns = _cols
