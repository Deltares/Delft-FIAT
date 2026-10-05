"""NetCDF writer driver.

A write driver for NetCDF grids built on top of the ``netCDF4`` Python API. Mirrors the
former ``NetcdfDriver`` write side: create (spatial) dimensions and variables, set the
spatial reference, and write windowed data. The geospatial metadata is exposed through a
shared :class:`fiat.driver.raster.GridProfile` attached as the ``profile`` attribute.
"""

from pathlib import Path

import netCDF4 as nc4
import numpy as np
from pyproj.crs import CRS

from fiat.driver.netcdf.reader import NetcdfVariable, check_state
from fiat.driver.raster import GridProfile
from fiat.util import NODATA_VALUE

__all__ = ["NetcdfWriter"]


class NetcdfWriter:
    """NetCDF grid write driver.

    Parameters
    ----------
    file : Path | str
        The path to the NetCDF file.
    crs : str, optional
        A user provided spatial reference system. By default None.
    """

    def __init__(
        self,
        file: Path | str,
        crs: str | None = None,
    ):
        # State and pathing
        self._closed = False
        self.path = Path(file)

        # Load the source
        self.src = nc4.Dataset(filename=file, mode="w")
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

    # Properties
    @property
    def closed(self) -> bool:
        """Return whether the dataset has been closed."""
        return self._closed

    @property
    def names(self) -> list[str]:
        """Return the names of the data variables."""
        return list(self.variables.keys())

    @property
    def size(self) -> int:
        """Return the number of data variables."""
        return len(self.variables)

    # I/O related
    def close(self) -> None:
        """Close the dataset."""
        self.flush()
        self._closed = True
        if self.src is not None:
            self.src.close()
        self.src = None

    def flush(self) -> None:
        """Flush the data."""
        if self.src is not None:
            self.src.sync()

    # Mutating methods
    @check_state
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

    @check_state
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
        self.profile = GridProfile(
            xvals=self.xdim[:],
            yvals=self.ydim[:],
            crs_wkt=self._crs,
        )

    @check_state
    def create_spatial_variable(
        self,
        var: str,
        dtype: str = "f4",
        nodata: float = NODATA_VALUE,
        compression: str = "zlib",
        complevel: int = 5,
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
        compression : str, optional
            The compression algorithm, by default "zlib".
        complevel : int, optional
            The compression level, by default 5.
        """
        data = self.src.createVariable(
            varname=var,
            datatype=dtype,
            dimensions=(self.ydim.name, self.xdim.name),
            fill_value=nodata,
            compression=compression,
            complevel=complevel,
        )
        data.setncattr("grid_mapping", self.reference.name)
        dv = NetcdfVariable._create(var=data, ref=self.src)
        self.variables[var] = dv
        self._variables.append(dv)

    @check_state
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
        if self.profile is not None:
            self.profile.crs_wkt = crs.to_wkt()
