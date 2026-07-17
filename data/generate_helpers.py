"""Some helper functions for creating the test data."""

from pathlib import Path

import netCDF4 as nc4
import numpy as np
from pyproj.crs import CRS

DATA_DIR = Path(__file__).parent


def netcdf_handle(
    fname: Path | str,
    lats: np.ndarray,
    lons: np.ndarray,
    crs: CRS | str | None = None,
) -> nc4.Dataset:
    """Simply create netcdf files."""
    # Open the file
    ds = nc4.Dataset(
        filename=Path(DATA_DIR, fname),
        mode="w",
    )
    # Create the spatial dimensions
    ds.createDimension(dimname="lat", size=len(lats))
    ds.createDimension(dimname="lon", size=len(lons))
    ydim = ds.createVariable(
        varname="lat",
        datatype="f4",
        dimensions=("lat",),
    )
    ydim[:] = np.sort(lats)[::-1]
    xdim = ds.createVariable(
        varname="lon",
        datatype="f4",
        dimensions=("lon",),
    )
    xdim[:] = np.sort(lons)

    if crs is None:
        return ds

    # Ensure typing
    if not isinstance(crs, CRS):
        crs = CRS.from_user_input(crs)

    reference = ds.createVariable("spatial_ref", datatype="i4")
    reference.setncatts({"x_dim": "lon", "y_dim": "lat"})
    reference.setncatts(
        {
            "crs_wkt": crs.to_wkt(),
            "spatial_ref": crs.to_wkt(),
        }
    )
    gtf = [lons[0], np.diff(lons).mean(), 0.0, lats[0], 0.0, np.diff(lats).mean()]
    gtf = [float(item) for item in gtf]
    reference.setncattr("GeoTransform", str(gtf).strip("[]").replace(",", ""))
    return ds


def netcdf_variable(
    ds: nc4.Dataset,
    name: str,
) -> nc4.Variable:
    """Simply create a netcdf variable in a dataset."""
    data = ds.createVariable(
        varname=name,
        datatype="f4",
        dimensions=("lat", "lon"),
        fill_value=-9999,
    )

    # Check if there is a spatial reference present
    if "spatial_ref" in ds.variables:
        data.setncattr("grid_mapping", "spatial_ref")
    return data
