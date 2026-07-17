"""Only raster methods for FIAT."""

import math
from pathlib import Path

import numpy as np
from pyproj import Transformer
from pyproj.crs import CRS
from scipy.interpolate import RegularGridInterpolator

from fiat.fio import Dataset


def transform_bounds(
    bounds: tuple[float, float, float, float],
    transformer: Transformer,
) -> tuple[float, float, float, float]:
    """Calculate the bounds in another projection.

    Parameters
    ----------
    bounds : tuple[float, float, float, float]
        The current bounds.
    transformer : Transformer
        The coordinate transformer.

    Returns
    -------
    tuple[float, float, float, float]
        The resulting bounds.
    """
    # Create the corners
    x_c = [bounds[0], bounds[2], bounds[0], bounds[2]]
    y_c = [bounds[1], bounds[1], bounds[3], bounds[3]]
    # Transform the corners
    x_c, y_c = transformer.transform(x_c, y_c)
    # Return the max extent
    return min(x_c), min(y_c), max(x_c), max(y_c)


def default_transform(
    transform: tuple[float, ...],
    width: int,
    height: int,
    transformer: Transformer,
    n_samples: int = 21,
) -> tuple[tuple[float, ...], int, int]:
    """Create a suggestion for the default transform.

    The function is close but not the same as GDAL's SuggestedWarpOutput.

    Parameters
    ----------
    transform : tuple[float, ...]
        The geotransform of the source data.
    width : int
        The width of the source data
    height : int
        The height of the source data.
    transformer : Transformer
        The coordinates transformer mapping one system to another.
    n_samples : int, optional
        The number of samples along the edges, by default 21

    Returns
    -------
    tuple[tuple[float, ...], int, int]
        The resulting geotransform, width & height in the targer coordinate system.
    """
    originx, dx, _, originy, _, dy = transform

    # Create the sample points along the axes
    samples_lon = np.linspace(0, width, n_samples)
    samples_lat = np.linspace(0, height, n_samples)

    xs = []
    ys = []
    # Origin horizontal
    xs.extend(originx + samples_lon * dx)
    ys.extend(np.full_like(samples_lon, originy))
    # Origin vertical
    xs.extend(np.full_like(samples_lat, originx))
    ys.extend(originy + samples_lat * dy)
    # Opposed horizontal
    xs.extend(originx + samples_lon * dx)
    ys.extend(np.full_like(samples_lon, originy + height * dy))
    # Opposed vertical
    xs.extend(np.full_like(samples_lat, originx + width * dx))
    ys.extend(originy + samples_lat * dy)

    # Transform all the samples for possibly the full extent
    xt, yt = transformer.transform(xs, ys)
    # Get the maximum extend
    xmin = float(np.min(xt))
    xmax = float(np.max(xt))
    ymin = float(np.min(yt))
    ymax = float(np.max(yt))

    # The inner distance based on the origin and opposing corner diagonally
    origin_t = transformer.transform(originx, originy)
    opposed_t = transformer.transform(originx + width * dx, originy + height * dy)
    dst_diag_inner = math.hypot(opposed_t[0] - origin_t[0], opposed_t[1] - origin_t[1])

    # Get the number of cells in diagonally (even though its not rounded)
    ncells = math.hypot(width, height)

    # First estimate of the destination resolution
    dst_res = dst_diag_inner / ncells
    # Get the first width and height estimate
    # dst_width = max(1, int((xmax - xmin) / dst_res + 0.5))
    # dst_height = max(1, int((ymax - ymin) / dst_res + 0.5))
    # # Get the resolution in both x and y direction
    # dst_res_x = (xmax - xmin) / dst_width
    # dst_res_y = (ymax - ymin) / dst_height
    # # Get max of the two as the final resolution
    # dst_res = max(dst_res_x, dst_res_y)

    # Set the output transform and the width and height
    dst_transform = (xmin, dst_res, 0.0, ymax, 0.0, -dst_res)
    dst_width = max(1, int((xmax - xmin) / dst_res + 0.5))
    dst_height = max(1, int((ymax - ymin) / dst_res + 0.5))

    return dst_transform, dst_width, dst_height


def reproject(
    ds: Dataset,
    dst_crs: CRS | str,
    dst_gtf: list | tuple = None,
    dst_width: int = None,
    dst_height: int = None,
    method: str = "nearest",
    output_dir: Path | str = None,
) -> Dataset:
    """Reproject (warp) a grid.

    Parameters
    ----------
    ds : Dataset
        Input object.
    dst_crs : CRS | str
        Coodinates reference system (projection). An accepted format is: `EPSG:3857`.
    dst_gtf : list | tuple, optional
        The geotransform of the warped dataset. Must be defined in the same
        coordinate reference system as dst_crs. When defined, its only used when
        both 'dst_width' and 'dst_height' are defined.
    dst_width : int, optional
        The width of the warped dataset in pixels.
    dst_height : int, optional
        The height of the warped dataset in pixels.
    method : str, optional
        Resampling method during warping.
    output_dir : Path | str, optional
        Output directory. If not defined, if will be inferred from the input object.

    Returns
    -------
    Dataset
        Output object. A lazy reading of the just creating raster file.
    """
    # Set the output path
    output_dir = Path(output_dir or ds.path.parent)
    write_path = Path(output_dir, f"{ds.path.stem}_repr.nc")

    # Setup the transformer
    transformer = Transformer.from_crs(ds.crs, dst_crs, always_xy=True)
    inverse_transformer = Transformer.from_crs(dst_crs, ds.crs, always_xy=True)

    # Calculate default transform if info is missing
    if any(item is None for item in [dst_gtf, dst_width, dst_height]):
        dst_gtf, dst_width, dst_height = default_transform(
            ds.transform,
            *ds.shape_xy,
            transformer,
            n_samples=21,
        )

    # Create the lons and lats in the middle of the cells in the target projection
    lons = np.arange(
        dst_gtf[0] + 0.5 * dst_gtf[1],
        dst_gtf[0] + dst_gtf[1] * dst_width,
        dst_gtf[1],
    )
    lats = np.arange(
        dst_gtf[3] + 0.5 * dst_gtf[5],
        dst_gtf[3] + dst_gtf[5] * dst_height,
        dst_gtf[5],
    )
    lons_grid, lats_grid = np.meshgrid(lons, lats)
    # Transform the cell coordinates back the source projection
    lons_src, lats_src = inverse_transformer.transform(lons_grid, lats_grid)
    lons_src = lons_src.clip(min=min(ds.xvals), max=max(ds.xvals))
    lats_src = lats_src.clip(min=min(ds.yvals), max=max(ds.yvals))

    # Setup the output dataset
    write_ds = Dataset(write_path, mode="w")
    write_ds.create_spatial_dims(lats=lats, lons=lons)
    write_ds.set_spatial_ref(CRS.from_user_input(dst_crs))

    # Loop though the variables
    for var, var_obj in ds.variables.items():
        # Create the spatial data variable
        write_ds.create_spatial_variable(var)
        # Get the data
        data = var_obj[:]
        data[data == var_obj.nodata] = np.nan

        # Set up the interpolator
        interpolator = RegularGridInterpolator(
            (ds.yvals, ds.xvals),  # NOTE: order = (lats, lons)
            data,
            method=method,
            bounds_error=False,
            fill_value=np.nan,
        )

        # Resample the data to the new coordinates (in source projection still)
        pts = np.stack([lats_src, lons_src], axis=-1)  # same order
        data_out: np.ndarray = interpolator(pts)
        data_out[np.isnan(data_out)] = -9999

        # Write the array to the dataset variable
        write_ds.variables[var].set(data_out, origin=[0, 0])

    # Close the writing dataset
    write_ds.close()
    write_ds = None

    return Dataset(write_path)
