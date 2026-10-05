"""NetCDF reader driver.

A read-only driver for NetCDF grids built on top of the ``netCDF4`` Python API. The
geospatial metadata lives in a shared :class:`fiat.driver.raster.GridProfile`, attached
as the ``profile`` attribute, so it can be reused by other raster drivers.

Data variables are read lazily: no array is materialised on open. A window is only read
from disk when it is requested, and :meth:`NetcdfVariable.read_window` can hold a window
in memory for repeated access.
"""

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

    def _resolve_crs_wkt(self) -> str | None:
        """Resolve the CRS as a WKT (or pyproj user-input) string."""
        if self.reference is not None:
            try:
                return self.reference.getncattr("crs_wkt")
            except AttributeError:
                return None
        return self._crs

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


class NetcdfVariable:
    """NetCDF variable wrapper with lazy, windowed reads.

    Instances are created through :meth:`NetcdfVariable._create`. Data is read from disk
    on demand; :meth:`read_window` can materialise and hold a window in memory.
    """

    def __init__(self):
        # Object itself
        self._obj_ref: weakref.ReferenceType | None = None
        self._obj: nc4.Variable | None = None

        # Attributes
        self._nodata: float | None = None

        # Held window cache
        self._cache: np.ndarray | None = None
        self._cache_sel: tuple | None = None
        raise AttributeError("No constructer defined")

    def __getitem__(
        self,
        select: slice | tuple[slice, slice],
    ):
        if self._cache is not None and select == self._cache_sel:
            return self._cache
        return self._obj[select]

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
        obj._cache = None
        obj._cache_sel = None

        obj._discover_attributes()

        return obj

    ## Properties
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

    ## Get methods
    def get_attr(self, var: str):
        """Get an attribute from the netcdf variable."""
        return self._obj.getncattr(name=var)

    def read_window(
        self,
        window: slice | tuple[slice, slice] | None = None,
        hold: bool = False,
    ) -> np.ndarray:
        """Read a window of data into memory.

        Parameters
        ----------
        window : slice | tuple[slice, slice] | None, optional
            The window to read. When None the full variable is read.
        hold : bool, optional
            When True the window is cached in memory so subsequent accesses of the same
            window are served from memory, by default False.

        Returns
        -------
        np.ndarray
            The requested data.
        """
        select = slice(None) if window is None else window
        data = self._obj[select]
        if hold:
            self._cache = data
            self._cache_sel = select
        return data

    def clear_window(self) -> None:
        """Release a held window from memory."""
        self._cache = None
        self._cache_sel = None

    ## Mutating methods
    def mask_nodata(self):
        """_summary_."""
        ...

    def set(
        self,
        data: np.ndarray,
        origin: tuple[float],
    ):
        """Set data in the variable."""
        shape = data.shape
        self._obj[origin[1] : shape[0], origin[0] : shape[1]] = data
