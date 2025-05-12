"""Base class structures."""

from abc import ABCMeta, abstractmethod

from fiat.util import DD_NEED_IMPLEMENTED


class BaseStruct(metaclass=ABCMeta):
    """A struct container."""

    def __init__(self):
        self._columns = {}
        self._kwargs = {}
        self._index = {}

    @abstractmethod
    def __del__(self):
        raise NotImplementedError(DD_NEED_IMPLEMENTED)

    def __repr__(self):
        _mem_loc = f"{id(self):#018x}".upper()
        return f"<{self.__class__.__name__} object at {_mem_loc}>"

    def _update_kwargs(
        self,
        **kwargs,
    ):
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
        Indices of the table object, by default None
    columns : tuple, optional
        Columns of the table object, by default None
    """

    def __init__(
        self,
        nrow: int,
        ncol: int,
        dtypes: list | tuple,
        index: tuple = None,
        columns: tuple = None,
        **kwargs,
    ) -> object:
        # Declarations
        self._columns = {}
        self._index = {}
        self._index_name = "index"
        self._ncol = ncol
        self._nrow = nrow
        self.dtypes = dtypes

        self._set_columns(columns)
        self._set_index(index, internal_index=kwargs.get("internal_index"))

    def __del__(self):
        pass

    def __len__(self):
        return self._nrow

    @abstractmethod
    def __getitem__(self, key):
        raise NotImplementedError(DD_NEED_IMPLEMENTED)

    ## Private methods
    def _set_columns(
        self,
        columns: list | tuple,
    ):
        """Set the columns at a base level."""
        if columns is None:
            columns = [f"col_{num}" for num in range(self.ncol)]
        if len(columns) != self.ncol:
            raise ValueError(f"Size of columns ({len(columns)}) not the same \
as the data ({self.ncol})")

        # Some checking in regards to duplicates in column headers
        self.columns_raw = columns

        # Create the column indexing
        self._columns = dict(zip(columns, range(self.ncol)))

    def _set_index(
        self,
        index: list | tuple | None,
        internal_index: list | tuple | None = None,
    ):
        """Set the index at a base level."""
        index_int = list(range(self.nrow))
        if internal_index is not None:
            index_int = internal_index

        if index is None:
            index = tuple(range(self.nrow))
        self._index = dict(zip(index, index_int))

    ## Properties
    @property
    def columns(self):
        """Return the columns."""
        return tuple(self._columns.keys())

    @property
    def index(self):
        """Return the row indices."""
        return tuple(self._index.keys())

    @property
    def index_name(self):
        """Return the name of the index."""
        return self._index_name

    @index_name.setter
    def index_name(self, value: str):
        """Set the name of the index."""
        self._index_name = value

    @property
    def ncol(self):
        """Return the number of columns."""
        return self._ncol

    @property
    def nrow(self):
        """Return the number of rows."""
        return self._nrow

    @property
    def shape(self):
        """Return the shape."""
        return (
            self.nrow,
            self.ncol,
        )
