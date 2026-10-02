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
    "fn_damage_structure": fgb.CT_STRING,
    "max_damage_structure": fgb.CT_DOUBLE,
}


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
):
    """Write a set of polygon WKTs to a FlatGeobuf file."""
    # Parse the crs
    crs_wkt, crs_org, crs_code = "", "", 0
    if epsg is not None:
        crs = CRS.from_epsg(code=epsg)
        crs_wkt = crs.to_wkt()
        crs_org, crs_code = "EPSG", epsg

    # Setup the writer
    writer = fgb.FlatGeobufWriter(
        path.as_posix(),
        col_names=list(fields.keys()),
        col_types=list(fields.values()),
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
        writer.add_feature(
            xy,
            ends,
            None,
            [idx + 1, f"fp_{idx + 1}", 0.0, dmc, (idx + 1) * 1000.0],
        )

    # Wrap it up
    writer.finalize()


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
