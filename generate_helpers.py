"""Some helper functions for creating the test data."""

import re
from pathlib import Path

import netCDF4 as nc4
import numpy as np
from pyproj.crs import CRS

from fiat.driver import fgb

DATA_DIR = Path(__file__).parent

# Exposure attribute columns and their FlatGeobuf ColumnType codes.
fields = {
    "object_id": fgb.CT_INT,
    "object_name": fgb.CT_STRING,
    "elevation": fgb.CT_DOUBLE,
}


def _impact_fields(types: tuple[str, ...]) -> dict:
    """Create the curve and maximum value columns per impact type."""
    out = {}
    for t in types:
        out[f"fn_{t}_structure"] = fgb.CT_STRING
        out[f"max_{t}_structure"] = fgb.CT_DOUBLE
    return out


def _polygon_wkt_to_arrays(wkt: str):
    """Parse a POLYGON WKT into flat ``xy`` coords and ring ``ends``."""
    body = wkt[wkt.index("(") + 1 : wkt.rindex(")")]
    xy = []
    ends = []
    for ring in re.findall(r"\(([^()]*)\)", body):
        for pair in ring.split(","):
            x, y = pair.split()
            xy.append(float(x))
            xy.append(float(y))
        ends.append(len(xy) // 2)
    return xy, ends


def fgb_writer(
    path: Path,
    name: str,
    geoms,
    epsg: int | None = None,
    types: tuple[str, ...] = ("damage",),
):
    """Write a set of polygon WKTs to a FlatGeobuf file.

    Every impact type gets its own curve and maximum value column; the maximum
    value of the n-th impact type is ``10**-n`` times that of the first.
    """
    # Parse the crs
    crs_wkt, crs_org, crs_code = "", "", 0
    if epsg is not None:
        crs = CRS.from_epsg(code=epsg)
        crs_wkt = crs.to_wkt()
        crs_org, crs_code = "EPSG", epsg

    # Setup the writer
    columns = fields | _impact_fields(types)
    writer = fgb.FlatGeobufWriter(
        path.as_posix(),
        col_names=list(columns.keys()),
        col_types=list(columns.values()),
        geom_type=fgb.GT_POLYGON,
        name=name,
        crs_wkt=crs_wkt,
        crs_org=crs_org,
        crs_code=crs_code,
    )

    # Loop through the geometries and translate them to arrays in order to write them
    for idx, wkt in enumerate(geoms):
        dmc = "struct_1" if (idx + 1) % 2 != 0 else "struct_2"
        xy, ends = _polygon_wkt_to_arrays(wkt)
        values = [idx + 1, f"fp_{idx + 1}", 0.0]
        for n, _ in enumerate(types):
            values += [dmc, (idx + 1) * 1000.0 / 10**n]
        writer.add_feature(
            xy,
            ends,
            None,
            values,
        )

    # Wrap it up
    writer.finalize()


def netcdf_handle(
    fname: Path | str,
) -> nc4.Dataset:
    """Simply create netcdf files."""
    # Open the file
    ds = nc4.Dataset(
        filename=Path(DATA_DIR, fname),
        mode="w",
    )
    return ds


def netcdf_dimension(
    ds,
    name: str,
    values: np.ndarray | list,
    dtype: str = "f4",
) -> None:
    """Create a dimensions."""
    # Create the dimension
    ds.createDimension(dimname=name, size=len(values))
    # Setup the variable
    dim = ds.createVariable(
        varname=name,
        datatype=dtype,
        dimensions=(name,),
    )
    dim[:] = values


def netcdf_spatial_dimensions(
    ds: nc4.Dataset,
    lats: np.ndarray,
    lons: np.ndarray,
    crs: CRS | str | None = None,
) -> None:
    """Create the spatial dimensions."""
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


def netcdf_spatial_variable(
    ds: nc4.Dataset,
    name: str,
    dtype: str = "f4",
    fill_value: float | int = -9999,
) -> nc4.Variable:
    """Simply create a spatial netcdf variable in a dataset."""
    data = ds.createVariable(
        varname=name,
        datatype=dtype,
        dimensions=("lat", "lon"),
        fill_value=fill_value,
    )

    # Check if there is a spatial reference present
    if "spatial_ref" in ds.variables:
        data.setncattr("grid_mapping", "spatial_ref")
    return data


def netcdf_variable(
    ds: nc4.Dataset,
    name: str,
    dims: tuple[str, ...],
    dtype: str = "f4",
    fill_value: float | int = -9999,
) -> nc4.Variable:
    """Simply create a netcdf variable in a dataset."""
    data = ds.createVariable(
        varname=name,
        datatype=dtype,
        dimensions=dims,
        fill_value=fill_value,
    )
    # Return the variable
    return data
