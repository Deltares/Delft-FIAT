"""Combined vector and raster methods for FIAT."""

from itertools import product

import numpy as np
from osgeo import ogr

from fiat.gis.util import pixel2world, world2pixel
from fiat.struct import GridBand


def intersect_cell(
    geom: ogr.Geometry,
    x: float | int,
    y: float | int,
    dx: float | int,
    dy: float | int,
):
    """Return where a geometry intersects with a cell.

    Parameters
    ----------
    geom : ogr.Geometry
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
    x = float(x)
    y = float(y)
    cell = ogr.Geometry(ogr.wkbPolygon)
    ring = ogr.Geometry(ogr.wkbLinearRing)
    ring.AddPoint(x, y)
    ring.AddPoint(x + dx, y)
    ring.AddPoint(x + dx, y + dy)
    ring.AddPoint(x, y + dy)
    ring.AddPoint(x, y)
    cell.AddGeometry(ring)
    return geom.Intersects(cell)


def mask(
    geom: ogr.Geometry,
    gtf: tuple,
    shape: tuple,
) -> tuple[tuple[int], np.ndarray[int]]:
    """Mask a grid based on a feature (vector).

    Parameters
    ----------
    ft : ogr.Geometry
        The Geometry according to the \
[ogr module](https://gdal.org/api/python/osgeo.ogr.html) of osgeo.
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
    minx, maxx, miny, maxy = geom.GetEnvelope()
    ulx, uly = world2pixel(gtf, minx, maxy)
    ulxn = min(max(0, ulx), ow - 1)
    ulyn = min(max(0, uly), oh - 1)
    lrx, lry = world2pixel(gtf, maxx, miny)
    lrxn = min(max(0, lrx), ow - 1)
    lryn = min(max(0, lry), oh - 1)
    plx, ply = pixel2world(gtf, ulx, uly)
    px_w = max(int(lrx - ulx) + 1 - abs(lrxn - lrx) - abs(ulxn - ulx), 0)
    px_h = max(int(lry - uly) + 1 - abs(lryn - lry) - abs(ulyn - uly), 0)

    window = (ulxn, ulyn, px_w, px_h)
    mask = np.ones((px_h, px_w))

    # Loop trough the cells
    for i, j in product(range(px_w), range(px_h)):
        if not intersect_cell(geom, plx + (dx * i), ply + (dy * j), dx, dy):
            mask[j, i] = 0

    return mask, window


def clip(band: GridBand, mask: np.ndarray[int], window: tuple[int]):
    """Clip a grid based on a feature (vector).

    Parameters
    ----------
    ft : ogr.Feature
        A Feature according to the \
[ogr module](https://gdal.org/api/python/osgeo.ogr.html) of osgeo.
        Can be optained by indexing a \
[GeomIO](/api/GeomIO.qmd).
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

    See Also
    --------
    - [clip_weighted](/api/overlay/clip_weighted.qmd)
    """
    # Use the window and mask to extract the data
    arr = band[*window][mask == 1]
    arr[arr == band.nodata] = np.nan
    return arr


def clip_weighted(
    ft: ogr.Feature,
    band: GridBand,
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
    ft : ogr.Feature
        A Feature according to the \
[ogr module](https://gdal.org/api/python/osgeo.ogr.html) of osgeo.
        Can be optained by indexing a \
[GeomIO](/api/GeomIO.qmd).
    band : GridBand
        An object that contains a connection the band within the dataset. For further
        information, see [GridBand](/api/GridBand.qmd)!
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
    geom = ft.GetGeometryRef()

    # Extract information
    dx = gtf[1]
    dy = gtf[5]
    minx, maxx, miny, maxy = geom.GetEnvelope()
    ulx, uly = world2pixel(gtf, minx, maxy)
    lrx, lry = world2pixel(gtf, maxx, miny)
    plx, ply = pixel2world(gtf, ulx, uly)
    dxn = dx / upscale
    dyn = dy / upscale
    px_w = int(lrx - ulx) + 1
    px_h = int(lry - uly) + 1
    clip = band[ulx, uly, px_w, px_h]
    mask = np.ones((px_h * upscale, px_w * upscale))

    # Loop trough the cells
    for i, j in product(range(px_w * upscale), range(px_h * upscale)):
        if not intersect_cell(geom, plx + (dxn * i), ply + (dyn * j), dxn, dyn):
            mask[j, i] = 0

    # Resample the higher resolution mask
    mask = mask.reshape((px_h, upscale, px_w, -1)).mean(3).mean(1)
    clip = clip[mask != 0]

    return clip, mask


def pin(
    point: tuple,
    band: GridBand,
    gtf: tuple,
) -> np.ndarray:
    """Pin a the value of a cell based on a coordinate.

    Parameters
    ----------
    point : tuple
        x and y coordinate.
    band : GridBand
        Input object. This holds a connection to the specified band.
    gtf : tuple
        The geotransform of a grid dataset.
        Has the following shape: (left, xres, xrot, upper, yrot, yres).

    Returns
    -------
    ndarray
        A NumPy array containing one value.
    """
    # Get metadata
    ow, oh = band.shape_xy

    # Get the coordinates
    x, y = world2pixel(gtf, *point)
    xn = int(0 <= x < ow)
    yn = int(0 <= y < oh)

    value = band[x, y, xn, yn]
    mask = np.ones(value.shape)  # This really is a dummy mask, but makes my life easy

    return value[mask == 1]
