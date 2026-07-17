"""Netcdf driver."""

import weakref
from pathlib import Path

import netCDF4 as nc4
import numpy as np
from pyproj.crs import CRS

from fiat.fio.base import BaseDriver
from fiat.util import NODATA_VALUE

__all__ = ["Dataset", "DataVariable"]


class Dataset(BaseDriver):
    """Simple netcdf dataset driver.

    Parameters
    ----------
    file : Path | str
        The path to the netcdf file.
    mode : str, optional
        The mode in which to open the file, by default "r".
    crs : str, optional
        A user provided spatial reference system if the dataset has none.
        By default None.
    """

    def __init__(
        self,
        file: Path | str,
        mode: str = "r",
        crs: str | None = None,
        mask: bool = True,
    ):
        # Supercharge
        BaseDriver.__init__(self, file, mode)
        # Load the source
        self.src = nc4.Dataset(filename=file, mode=mode)
        self.src.set_auto_mask(False)
        self.src.set_auto_scale(False)

        # Attributes
        self._crs: str | None = crs
        self.gtf: tuple[float] | None = None
        self.ydim: nc4.Variable | None = None
        self.yvals: np.ndarray | None = None
        self.xdim: nc4.Variable | None = None
        self.xvals: np.ndarray | None = None
        self.reference: nc4.Variable | None = None
        self.variables: dict[str, DataVariable] = {}
        self._variables: list[DataVariable] = []

        if self.mode <= 1:
            self._discover_variables()

    def __del__(self): ...

    def __getitem__(self, idx: int):
        return self._variables[idx]

    def __reduce__(self):
        return self.__class__, (
            self.path,
            self.mode_str,
            self._crs,
        )

    # Internals
    def _discover_reference(self) -> None:
        try:
            var = next(
                item for item in ["spatial_ref", "crs"] if item in self.src.variables
            )
            self.reference = self.src.variables[var]
        except StopIteration:
            ...

    def _discover_spatial_dims(self) -> None:
        if self.xdim is not None and self.ydim is not None:
            return
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
            self._set_spatial_dim_values()
        except StopIteration:
            raise ValueError("Couldn't derive the spatial dimensions")

    def _discover_variables(self) -> None:
        self._discover_reference()
        crs_var = self.reference.name if self.reference is not None else None
        for var_name, var in self.src.variables.items():
            if var_name in self.src.dimensions or var_name == crs_var:
                continue
            if var_name not in self.variables:
                self.variables[var_name] = DataVariable._create(var, self)
        self._variables = list(self.variables.values())

    def _set_spatial_dim_values(self) -> None:
        self.yvals = self.ydim[:].data
        self.xvals = self.xdim[:].data

    # Properties
    @property
    def bounds(self) -> tuple[float, ...]:
        """Return the bounds of the data."""
        gtf = self.transform
        xmin, xmax = sorted([gtf[0], gtf[0] + gtf[1] * self.xdim.size])
        ymin, ymax = sorted([gtf[3] + gtf[5] * self.ydim.size, gtf[3]])
        return (xmin, ymin, xmax, ymax)

    @property
    def crs(self) -> CRS | None:
        """Return the coordinate reference system."""
        if self.reference is not None:
            return CRS.from_user_input(self.reference.getncattr("crs_wkt"))
        return CRS.from_user_input(self._crs) if self._crs is not None else None

    @property
    def names(self) -> list[str]:
        """Return the names of the data variables."""
        return list(self.variables.keys())

    @property
    def origin(self) -> tuple[float, float]:
        """Return the origin of the grid."""
        dx, dy = self.res
        xs, ys = self.xvals, self.yvals
        x0, y0 = xs[0] - dx / 2, ys[0] - dy / 2
        return float(x0), float(y0)

    @property
    def res(self) -> tuple[float]:
        """Return the resolution of the data."""
        self._discover_spatial_dims()
        dxs, dys = np.diff(self.xvals), np.diff(self.yvals)
        dx, dy = dxs.mean(), dys.mean()
        return float(dx), float(dy)

    @property
    @BaseDriver.check_state
    def shape(self) -> tuple[int, int]:
        """Return the shape of the raster (y, x)."""
        self._discover_spatial_dims()
        return self.ydim.size, self.xdim.size

    @property
    @BaseDriver.check_state
    def shape_xy(self) -> tuple[int, int]:
        """Return the shape of the raster (x, y)."""
        self._discover_spatial_dims()
        return self.xdim.size, self.ydim.size

    @property
    def size(self) -> int:
        """Return the number of data variables."""
        return len(self.variables)

    @property
    def transform(self) -> tuple[float, ...]:
        """Return the geotransform of the data."""
        origin = self.origin
        res = self.res
        return (origin[0], res[0], 0.0, origin[1], 0.0, res[1])

    # I/O related
    def close(self) -> None:
        """Close the dataset."""
        BaseDriver.close(self)
        self.src.close()
        self.src = None

    def flush(self) -> None:
        """Flush the data."""
        self.src.sync()

    # Mutating methods
    @BaseDriver.check_mode
    @BaseDriver.check_state
    def create_dim(
        self,
        dim: str,
        size: int,
    ) -> None:
        """Create a dimension.

        Parameters
        ----------
        dim : str
            The name of the dimension.
        size : int
            The size of the dimension.
        """
        self.src.createDimension(dimname=dim, size=size)

    @BaseDriver.check_mode
    @BaseDriver.check_state
    def create_spatial_dims(
        self,
        lats: np.ndarray,
        lons: np.ndarray,
    ) -> None:
        """Create the spatial dimensions.

        Parameters
        ----------
        lats : np.ndarray
            The latitude values.
        lons : np.ndarray
            The longitude values.
        """
        self.src.createDimension(dimname="lat", size=len(lats))
        self.src.createDimension(dimname="lon", size=len(lons))
        self.ydim = self.src.createVariable(
            varname="lat",
            datatype="f8",
            dimensions=("lat",),
        )
        self.ydim[:] = lats
        self.xdim = self.src.createVariable(
            varname="lon",
            datatype="f8",
            dimensions=("lon",),
        )
        self.xdim[:] = lons
        self._set_spatial_dim_values()

    @BaseDriver.check_mode
    @BaseDriver.check_state
    def create_spatial_variable(
        self,
        var: str,
        dtype: str = "f4",
        nodata: float = NODATA_VALUE,
    ) -> None:
        """Create a spatial variable.

        Parameters
        ----------
        var : str
            The name of the variable.
        dtype : str, optional
            The data type of the variable according to netCDF, by default "f4".
        nodata : float, optional
            The nodata value of the variable, by default -9999.
        """
        self._discover_spatial_dims()
        data = self.src.createVariable(
            varname=var,
            datatype=dtype,
            dimensions=(self.ydim.name, self.xdim.name),
            fill_value=nodata,
        )
        data.setncattr("grid_mapping", self.reference.name)
        dv = DataVariable._create(var=data, ref=self.src)
        self.variables[var] = dv
        self._variables.append(dv)

    @BaseDriver.check_mode
    @BaseDriver.check_state
    def set_spatial_ref(
        self,
        crs: CRS,
    ) -> None:
        """Set the spatial reference system for the dataset.

        Parameters
        ----------
        crs : CRS
            The coordinate reference system (CRS) to set.
        """
        self.reference = self.src.createVariable("spatial_ref", datatype="i4")
        self.reference.setncatts({"x_dim": self.xdim.name, "y_dim": self.ydim.name})
        self.reference.setncatts(
            {
                "crs_wkt": crs.to_wkt(),
                "spatial_ref": crs.to_wkt(),
            }
        )


class DataVariable:
    """Netcdf variable wrapper."""

    def __init__(
        self,
    ):
        # Object itself
        self._obj_ref: weakref.ReferenceType | None = None
        self._obj: nc4.Variable | None = None

        # Attributes
        self._data: np.ndarray | None = None
        self._nodata: float | None = None
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
        obj = DataVariable.__new__(cls)
        obj._obj_ref = weakref.ref(ref, obj._cleanup)
        obj._obj = var

        obj._discover_attributes()
        obj._data = obj._obj[:] 

        return obj

    ## Properties
    @property
    def dtype(self) -> str:
        """Return the data type of the variable."""
        return self._obj.datatype

    ## Properties
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
        """Get am attribute from the netcdf variable."""
        return self._obj.getncattr(name=var)

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
