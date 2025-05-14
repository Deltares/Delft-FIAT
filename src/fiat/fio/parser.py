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
        handler: BufferHandler,
        delimiter: str,
        header: bool,
        index: str | None = None,
    ):
        # The internal variables
        self.columns: list = None
        self.delimiter: str = delimiter
        self.data: BufferHandler = handler
        self.dtypes: list = None
        self.duplicates: list = None
        self.index: list = None
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
    ):
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
                if len(t) == 1:
                    tl = t[0].split(":")
                    if len(tl) > 1:
                        # Iterables in the metadata
                        lst = tl[1].split(self.delimiter)
                        entry = tl[0].strip().replace("#", "").lower()
                        val = [item.strip() for item in lst]
                        self.meta[entry] = val
                    else:
                        # Direct key value pairs
                        lst = t[0].split(self.delimiter)
                        entry = lst[0].strip().replace("#", "").lower()
                        val = [item.strip() for item in lst[1:]]
                        self.meta[entry] = val
                        # raise ValueError("Supplied metadata in unknown format..")
                else:
                    # Really direct key value pairs
                    key, item = t
                    self.meta[key.strip().replace("#", "").lower()] = item.strip()
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
    ):
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

    def resolve_column_headers(self):
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
