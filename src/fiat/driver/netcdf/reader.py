"""NetCDF reader."""

import weakref
from pathlib import Path

import netCDF4 as nc4
import numpy as np

from fiat.driver.raster import GridProfile

__all__ = ["NetcdfReader", "NetcdfVariable"]


def check_state(m):
    """Guard a method against being called on a closed driver."""

    def _inner(self, *args, **kwargs):
        if self.closed:
            raise ValueError("Invalid operation on a closed file")
        return m(self, *args, **kwargs)

    return _inner


class NetcdfVariable:
    """NetCDF variable wrapper with lazy, windowed reads."""

    def __init__(self):
        # Object itself
        self._obj_ref: weakref.ReferenceType | None = None
        self._obj: nc4.Variable | None = None

        # Attributes
        self._nodata: float | None = None

        # Held data in memory
        self._data: np.ndarray | None = None
        raise AttributeError("No constructer defined")

    def __getitem__(
        self,
        select: slice | tuple[slice, slice],
    ):
        return self._data[select]

    ## Private methods
    def _cleanup(self, weak_ref):
        self._obj = None

    def _discover_attributes(self):
        self._nodata = self._obj.__dict__.get("_FillValue")

    @classmethod
    def _create(
        cls,
        var: nc4.Variable,
        ref: nc4.Dataset,
    ):
        obj = NetcdfVariable.__new__(cls)
        obj._obj_ref = weakref.ref(ref, obj._cleanup)
        obj._obj = var
        obj._nodata = None
        obj._data = None

        obj._discover_attributes()

        return obj

    ## Properties
    @property
    def data(self) -> np.ndarray | None:
        """Return the in memory data."""
        return self._data

    @property
    def dtype(self) -> str:
        """Return the data type of the variable."""
        return self._obj.datatype

    @property
    def name(self) -> str:
        """Return the name of the variable."""
        return self._obj.name

    @property
    def nodata(self) -> float | None:
        """Return the nodata value."""
        return self._nodata

    @property
    def is_spatial(self) -> bool:
        """Return whether the variable is a spatial one."""
        ...

    ## I/O methods
    def clear(self) -> None:
        """Release data from memory."""
        self._data = None

    def load(
        self,
        *window: tuple[slice, ...],
    ) -> np.ndarray:
        """Load a window of data into memory.

        Parameters
        ----------
        window : tuple[slice, ...], optional
            The window to read. When no extend is provided, the full variable is read.
        """
        select = (slice(None),) if not window else window
        data = self._obj[*select]
        self._data = data
        return self._data

    ## Get methods
    def get_attr(self, var: str):
        """Get an attribute from the netcdf variable."""
        return self._obj.getncattr(name=var)

    ## Mutating methods
    def set(
        self,
        data: np.ndarray,
        origin: tuple[float],
    ):
        """Set data in the variable."""
        shape = data.shape
        self._obj[
            origin[1] : origin[1] + shape[0],
            origin[0] : origin[0] + shape[1],
        ] = data


class NetcdfReader:
    """Read-only NetCDF grid driver.

    Parameters
    ----------
    file : Path | str
        The path to the NetCDF file.
    crs : str, optional
        A user provided spatial reference system if the dataset has none.
        By default None.
    mask : bool, optional
        Kept for API compatibility (netCDF4 auto-masking is disabled).
    """

    def __init__(
        self,
        file: Path | str,
        crs: str | None = None,
        mask: bool = True,
    ):
        # State and pathing
        self._closed = False
        self.path = Path(file)
        if not self.path.is_file():
            raise FileNotFoundError(
                f"{self.path.as_posix()} doesn't exist, can't read",
            )

        # Load the source
        self.src = nc4.Dataset(filename=file, mode="r")
        self.src.set_auto_mask(False)
        self.src.set_auto_scale(False)

        # Attributes
        self._crs: str | None = crs
        self._variables: list[NetcdfVariable] = []
        self.profile: GridProfile | None = None
        self.reference: nc4.Variable | None = None
        self.xdim: nc4.Variable | None = None
        self.ydim: nc4.Variable | None = None
        self.variables: dict[str, NetcdfVariable] = {}

        self._discover_variables()
        self._discover_spatial_dims()

    def __del__(self): ...

    def __getitem__(self, idx: int):
        return self._variables[idx]

    def __iter__(self):
        return iter(self._variables)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def __reduce__(self):
        return self.__class__, (
            self.path,
            self._crs,
        )

    # Internals
    def _discover_reference(self) -> None:
        """Discover the spatial reference variable."""
        try:
            var = next(
                item for item in ["spatial_ref", "crs"] if item in self.src.variables
            )
            self.reference = self.src.variables[var]
        except StopIteration:
            ...

    def _resolve_crs_wkt(self) -> str | None:
        """Resolve the CRS as a WKT (or pyproj user-input) string."""
        if self.reference is not None:
            try:
                return self.reference.getncattr("crs_wkt")
            except AttributeError:
                return None
        return self._crs

    def _discover_spatial_dims(self) -> None:
        """Discover the spatial dimensions of the dataset and build the profile."""
        try:
            yvar = next(
                item for item in ["y", "lat", "latitude"] if item in self.src.dimensions
            )
            xvar = next(
                item
                for item in ["x", "lon", "longitude"]
                if item in self.src.dimensions
            )
            self.ydim = self.src.variables[yvar]
            self.xdim = self.src.variables[xvar]
        except StopIteration:
            raise ValueError("Couldn't derive the spatial dimensions")

        self.profile = GridProfile(
            xvals=self.xdim[:],
            yvals=self.ydim[:],
            crs_wkt=self._resolve_crs_wkt(),
        )

    def _discover_variables(self) -> None:
        """Discover the dataset data variables."""
        self._discover_reference()
        crs_var = self.reference.name if self.reference is not None else None
        for var_name, var in self.src.variables.items():
            if var_name in self.src.dimensions or var_name == crs_var:
                continue
            if var_name not in self.variables:
                self.variables[var_name] = NetcdfVariable._create(var, self.src)
        self._variables = list(self.variables.values())

    # Properties
    @property
    def names(self) -> list[str]:
        """Return the names of the data variables."""
        return list(self.variables.keys())

    @property
    @check_state
    def size(self) -> int:
        """Return the number of data variables."""
        return len(self.variables)

    # I/O related
    @property
    def closed(self) -> bool:
        """Return whether the dataset has been closed."""
        return self._closed

    def close(self) -> None:
        """Close the dataset."""
        self.flush()
        self._closed = True
        if self.src is not None:
            self.src.close()
        self.src = None

    def flush(self) -> None:
        """No-op for a read-only dataset."""

    def load(
        self,
        *window: tuple[slice, ...],
    ) -> None:
        """Load spatial variables into memory."""
        for var in self._variables:
            _ = var.load(*window)
