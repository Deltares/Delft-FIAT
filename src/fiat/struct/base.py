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
        index: tuple = None,
        columns: tuple = None,
        **kwargs,
    ) -> object:
        # Declarations
        self.dtypes = ()
        self.meta = kwargs
        self.index_col = -1

        # Set the attributes of the object
        for key, item in kwargs.items():
            if not key.startswith("_"):
                self.__setattr__(key, item)

        # Get the index integer ids
        index_int = list(range(kwargs["nrow"]))
        if "_index_int" in kwargs:
            index_int = kwargs.pop("_index_int")

        if columns is None:
            columns = [f"col_{num}" for num in range(kwargs["ncol"])]

        # Some checking in regards to duplicates in column headers
        self.columns_raw = columns

        # Create the column indexing
        self._columns = dict(zip(columns, range(kwargs["ncol"])))

        if index is None:
            index = tuple(range(kwargs["nrow"]))
        self._index = dict(zip(index, index_int))

    def __del__(self):
        pass

    def __len__(self):
        return self.meta["nrow"]

    @abstractmethod
    def __getitem__(self, key):
        raise NotImplementedError(DD_NEED_IMPLEMENTED)

    @property
    def columns(self):
        """Return the columns."""
        return tuple(self._columns.keys())

    @property
    def index(self):
        """Return the row indices."""
        return tuple(self._index.keys())

    @property
    def shape(self):
        """Return the shape."""
        return (
            self.meta["nrow"],
            self.meta["ncol"],
        )
