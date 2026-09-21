"""Base object of drivers."""

import gc
from abc import ABCMeta, abstractmethod
from pathlib import Path

from fiat.util import DD_NEED_IMPLEMENTED, NEED_IMPLEMENTED


class BaseDriver(metaclass=ABCMeta):
    """Base class for objects concerning I/O.

    Parameters
    ----------
    file : Path | str
        Path to the file
    mode : str, optional
        Mode in which to open the file, by default "r"
    """

    _mode_map = {
        "r": 0,
        "a": 1,
        "w": 2,
    }

    def __init__(
        self,
        file: Path | str,
        mode: str = "r",
    ):
        # Current state
        self._closed = False

        # Set the pathing
        self.path: Path = Path(file)

        # Check the mode
        if mode not in BaseDriver._mode_map:
            raise ValueError("Invalid mode, chose from 'r', 'a' or 'w'")

        # Set the mode
        self.mode: int = BaseDriver._mode_map[mode]
        self.mode_str: str = mode

        # If read and file doesnt exist, throw error
        if self.mode != 2 and not self.path.is_file():
            raise FileNotFoundError(
                f"{self.path.as_posix()} doesn't exist, can't read",
            )

    def __repr__(self):
        _mem_loc = f"{id(self):#018x}".upper()
        return f"<{self.__class__.__name__} object at {_mem_loc}>"

    def __hash__(self) -> int:
        return hash(self.path)

    def __del__(self):
        if not self.closed:
            self.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def check_mode(m):  # noqa : D102
        def _inner(self, *args, **kwargs):
            if not self.mode:
                raise ValueError("Invalid operation on a read-only file")
            _result = m(self, *args, **kwargs)

            return _result

        return _inner

    def check_state(m):  # noqa : D102
        def _inner(self, *args, **kwargs):
            if self.closed:
                raise ValueError("Invalid operation on a closed file")
            _result = m(self, *args, **kwargs)

            return _result

        return _inner

    def close(self) -> None:
        """Close the dataset/ stream."""
        self.flush()
        self._closed = True
        gc.collect()

    @property
    def closed(self) -> bool:
        """Return the state."""
        return self._closed

    @abstractmethod
    def flush(self) -> None:
        """Flush the buffer."""
        raise NotImplementedError(NEED_IMPLEMENTED)


class NamedIndex(dict):
    """Simple named indexing for tables..

    Parameters
    ----------
    settings : dict, optional
        The settings, by default {}.
    """

    def __init__(self, settings={}, **kwargs):
        dict.__init__(self, settings, **kwargs)
        self._name: str = "index"

    @property
    def name(self) -> str:
        """Return the index name."""
        return self._name

    @name.setter
    def name(self, value: str):
        """Set the name of the index."""
        self._name = value


class BaseStruct(metaclass=ABCMeta):
    """A struct container."""

    def __init__(self):
        self._columns: dict = {}
        self._kwargs: dict = {}
        self._index: NamedIndex = NamedIndex()

    @abstractmethod
    def __del__(self):
        raise NotImplementedError(DD_NEED_IMPLEMENTED)

    def __repr__(self):
        _mem_loc = f"{id(self):#018x}".upper()
        return f"<{self.__class__.__name__} object at {_mem_loc}>"

    ## Properties
    @property
    def columns(self) -> tuple:
        """Return the columns."""
        return tuple(self._columns.keys())

    @property
    def index(self) -> tuple:
        """Return the row indices."""
        return tuple(self._index.keys())

    @property
    def index_name(self) -> str:
        """Return the name of the index."""
        return self._index.name

    @index_name.setter
    def index_name(self, value: str):
        """Set the name of the index."""
        self._index.name = value

    @property
    def kwargs(self) -> dict:
        """Return internal kwargs."""
        return self._kwargs

    ## Methods
    def update_kwargs(
        self,
        **kwargs,
    ) -> None:
        """Update the keyword arguments.

        Only for internal use.
        """
        self._kwargs.update(
            **kwargs,
        )


class TableBase(BaseStruct, metaclass=ABCMeta):
    """Base class for table objects.

    Parameters
    ----------
    index : tuple, optional
        Indices of the table object, by default None.
    columns : tuple, optional
        Columns of the table object, by default None.
    """

    def __init__(
        self,
        nrow: int,
        ncol: int,
        dtypes: list | tuple,
        index: tuple | None = None,
        columns: tuple | None = None,
        **kwargs,
    ) -> object:
        # Supercharge
        BaseStruct.__init__(self)

        # Declarations
        self._ncol: int = ncol
        self._nrow: int = nrow
        self.dtypes: list = dtypes
        self.duplicate_columns: dict | None = None

        # Set the columns and index
        self._set_columns(columns)
        internal_index = None
        if "internal_index" in kwargs:
            internal_index = kwargs.pop("internal_index")
        self._set_index(index, internal_index=internal_index)

        # Set attributes where possible, otherwise just set them in the internal dict
        for key, item in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, item)
        self.update_kwargs(**kwargs)

    def __del__(self): ...

    def __len__(self) -> int:
        return self._nrow

    @abstractmethod
    def __getitem__(self, key):
        raise NotImplementedError(DD_NEED_IMPLEMENTED)

    ## Private methods
    def _set_columns(
        self,
        columns: list | tuple,
    ) -> None:
        """Set the columns at a base level."""
        if columns is None:
            columns = [f"col_{num}" for num in range(self.ncol)]
        if len(columns) != self.ncol:
            raise ValueError(f"Size of columns ({len(columns)}) not the same \
as the data ({self.ncol})")

        # Create the column indexing
        self._columns = dict(zip(columns, range(self.ncol)))

    def _set_index(
        self,
        index: list | tuple | None,
        name: str | None = None,
        internal_index: list | tuple | None = None,
    ) -> None:
        """Set the index at a base level."""
        index_int = list(range(self.nrow))
        if internal_index is not None:
            index_int = internal_index

        if index is None:
            index = tuple(range(self.nrow))
        self._index = NamedIndex(dict(zip(index, index_int)))
        if name is not None:
            self._index.name = name

    ## Properties
    @property
    def ncol(self) -> int:
        """Return the number of columns."""
        return self._ncol

    @property
    def nrow(self) -> int:
        """Return the number of rows."""
        return self._nrow

    @property
    def shape(self) -> tuple[int]:
        """Return the shape."""
        return (
            self.nrow,
            self.ncol,
        )

    ## Methods
    @abstractmethod
    def set_index(
        self,
        index_col: int | str,
    ) -> int:
        """Set the index to a new column."""
        # Check whether the index column index is valid
        if isinstance(index_col, str):
            index_col = self._columns.get(index_col, -1)
        if index_col >= 0 and index_col not in range(len(self.columns)):
            raise ValueError(f"Index column index out of range: ({index_col})")
        return index_col
