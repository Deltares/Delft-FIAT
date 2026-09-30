"""Combined vector and raster methods for FIAT."""

from itertools import product

import numpy as np

from fiat._core import cell_mask, clip_masked
from fiat.driver.fgb import GT_MULTIPOLYGON, GT_POLYGON, Feature, Geometry
from fiat.driver.netcdf import NetcdfVariable
from fiat.gis import _geom
from fiat.gis.geom import point_in_geom
from fiat.gis.util import pixel2world, world2pixel


def intersect_cell(
    geom: Geometry,
    x: float | int,
    y: float | int,
    dx: float | int,
    dy: float | int,
) -> bool:
    """Return where a geometry intersects with a cell.

    Parameters
    ----------
    geom : Geometry
        The geometry.
    x : float | int
        Left side of the cell.
    y : float | int
        Upper side of the cell.
    dx : float | int
        Width of the cell.
    dy : float | int
        Height of the cell.
    """
    return _geom.intersect_cell(geom, float(x), float(y), float(dx), float(dy))


def area_mask(
    geom: Geometry,
    gtf: tuple[float, ...],
    shape: tuple[int, int],
) -> tuple[np.ndarray, tuple[int, ...]]:
    """Mask a grid based on a geometry (vector).

    Parameters
    ----------
    geom : Geometry
        The geometry.
    gtf : tuple
        The geotransform of a grid dataset.
        Has the following shape: (left, xres, xrot, upper, yrot, yres).
    shape : tuple
        The shape of the grid dataset set (width, height).

    Returns
    -------
    tuple
        An array containing the polygon mask and a tuple containing the location of the
        polygon window in the grid.
    """
    # Get the geometry information form the feature
    ow, oh = shape

    # Extract information
    dx = gtf[1]
    dy = gtf[5]
    minx, miny, maxx, maxy = geom.envelope()
    ulx, uly = world2pixel(gtf, minx, maxy)
    ulxn = min(max(0, ulx), ow - 1)
    ulyn = min(max(0, uly), oh - 1)
    lrx, lry = world2pixel(gtf, maxx, miny)
    lrxn = min(max(0, lrx), ow - 1)
    lryn = min(max(0, lry), oh - 1)
    plx, ply = pixel2world(gtf, ulx, uly)
    px_w = max(int(lrx - ulx) + 1 - abs(lrxn - lrx) - abs(ulxn - ulx), 0)
    px_h = max(int(lry - uly) + 1 - abs(lryn - lry) - abs(ulyn - uly), 0)

    window = slice(ulyn, ulyn + px_h), slice(ulxn, ulxn + px_w)

    # Rasterise the footprint of the geometry over the window in C.
    xy = np.ascontiguousarray(geom.xy, dtype=np.float64)
    ends = np.ascontiguousarray(geom.ends, dtype=np.uint32)
    if ends.shape[0] == 0:
        # Single implicit ring/line spanning all coordinate pairs.
        ends = np.array([xy.shape[0] // 2], dtype=np.uint32)
    is_areal = 1 if geom.type in (GT_POLYGON, GT_MULTIPOLYGON) else 0
    mask = cell_mask(xy, ends, is_areal, plx, ply, dx, dy, px_w, px_h)

    return mask, window


def point_mask(
    point: tuple,
    gtf: tuple[float, ...],
    shape: tuple[int, int],
) -> tuple[tuple[int], np.ndarray]:
    """Create a mask of a point on a grid.

    Parameters
    ----------
    point : tuple
        x and y coordinate.
    gtf : tuple
        The geotransform of a grid dataset.
        Has the following shape: (left, xres, xrot, upper, yrot, yres).
    shape : tuple
        The shape of the grid dataset set (width, height).

    Returns
    -------
    tuple
        An array containing the polygon mask and a tuple containing the location of the
        polygon window in the grid.
    """
    # Get metadata
    ow, oh = shape

    # Get the coordinates
    x, y = world2pixel(gtf, *point)
    xn = int(0 <= x < ow)
    yn = int(0 <= y < oh)

    # Setup the mask and window
    window = slice(y, y + yn), slice(x, x + xn)
    mask = np.ones((yn, xn))  # This really is a dummy mask, but makes my life easy

    return mask, window


def centroid_mask(
    geom: Geometry,
    gtf: tuple[float, ...],
    shape: tuple[int, int],
) -> tuple[tuple[int], np.ndarray]:
    """Get point mask based on centroid of e.g. a polygon geometry.

    Parameters
    ----------
    geom : Geometry
        The geometry.
    gtf : tuple
        The geotransform of a grid dataset.
        Has the following shape: (left, xres, xrot, upper, yrot, yres).
    shape : tuple
        The shape of the grid dataset set (width, height).

    Returns
    -------
    tuple
        An array containing the polygon mask and a tuple containing the location of the
        polygon window in the grid.
    """
    # Get the x,y coordinates
    point = point_in_geom(geometry=geom)
    return point_mask(point=point, gtf=gtf, shape=shape)


def clip(
    var: NetcdfVariable,
    mask: np.ndarray,
    window: tuple[int, ...],
) -> np.ndarray:
    """Clip a grid based on a mask.

    The mask is the geometry's footprint on the raster.

    Parameters
    ----------
    var : NetcdfVariable
        The raster variable.
    mask : np.ndarray[int]
        The mask of the geometry within the window of the geometry.
    window : tuple[int]
        The window that the geometry covers of the raster (variable).

    Returns
    -------
    np.ndarray
        The resulting values.

    See Also
    --------
    - [clip_weighted](/api/overlay/clip_weighted.qmd)
    """
    # Gather the masked cells and map nodata -> nan in one compiled pass.
    arr = var[*window]
    if np.issubdtype(arr.dtype, np.floating):
        has_nodata = var.nodata is not None
        return clip_masked(
            arr,
            mask,
            float(var.nodata) if has_nodata else 0.0,
            1 if has_nodata else 0,
        )
    # Fallback for non-floating (e.g. integer) grids: keep numpy semantics.
    return arr[mask == 1]


def clip_weighted(
    ft: Feature,
    var: NetcdfVariable,
    gtf: tuple,
    upscale: int = 3,
):
    """Clip a grid based on a feature (vector), but weighted.

    This method caters to those who wish to have information about the percentages of \
cells that are touched by the feature.

    Warnings
    --------
    A high upscale value comes with a calculation penalty!
    Geometry needs to be inside the grid!

    Parameters
    ----------
    ft : Feature
        A feature from a [GeomDriver](/api/GeomDriver.qmd).
    var : NetcdfVariable
        An object that contains a connection the variable within the dataset.
        For further information, see [NetcdfVariable](/api/NetcdfVariable.qmd)!
    gtf : tuple
        The geotransform of a grid dataset.
        Has the following shape: (left, xres, xrot, upper, yrot, yres).
    upscale : int, optional
        How much the underlying grid will be upscaled.
        The higher the value, the higher the accuracy.

    Returns
    -------
    array
        A 1D array containing the clipped values.

    See Also
    --------
    - [clip](/api/overlay/clip.qmd)
    """
    geom = ft.geometry

    # Extract information
    dx = gtf[1]
    dy = gtf[5]
    minx, miny, maxx, maxy = geom.envelope()
    ulx, uly = world2pixel(gtf, minx, maxy)
    lrx, lry = world2pixel(gtf, maxx, miny)
    plx, ply = pixel2world(gtf, ulx, uly)
    dxn = dx / upscale
    dyn = dy / upscale
    px_w = int(lrx - ulx) + 1
    px_h = int(lry - uly) + 1
    clip = var[uly : uly + px_h, ulx : ulx + px_w]
    mask = np.ones((px_h * upscale, px_w * upscale))

    # Loop trough the cells
    for i, j in product(range(px_w * upscale), range(px_h * upscale)):
        if not intersect_cell(geom, plx + (dxn * i), ply + (dyn * j), dxn, dyn):
            mask[j, i] = 0

    # Resample the higher resolution mask
    mask = mask.reshape((px_h, upscale, px_w, -1)).mean(3).mean(1)
    clip = clip[mask != 0]

    return clip, mask
