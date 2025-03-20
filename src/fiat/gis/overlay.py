"""Combined vector and raster methods for FIAT."""

from itertools import product

from numpy import ndarray, ones
from osgeo import ogr

from fiat.fio import Grid
from fiat.gis.util import pixel2world, world2pixel


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


def clip(
    ft: ogr.Feature,
    band: Grid,
    gtf: tuple,
):
    """Clip a grid based on a feature (vector).

    Parameters
    ----------
    ft : ogr.Feature
        A Feature according to the \
[ogr module](https://gdal.org/api/python/osgeo.ogr.html) of osgeo.
        Can be optained by indexing a \
[GeomSource](/api/GeomSource.qmd).
    band : Grid
        An object that contains a connection the band within the dataset. For further
        information, see [Grid](/api/Grid.qmd)!
    gtf : tuple
        The geotransform of a grid dataset.
        Has the following shape: (left, xres, xrot, upper, yrot, yres).

    Returns
    -------
    array
        A 1D array containing the clipped values.

    See Also
    --------
    - [clip_weighted](/api/overlay/clip_weighted.qmd)
    """
    # Get the geometry information form the feature
    geom = ft.GetGeometryRef()
    ow, oh = band.shape_xy

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

    clip = band[ulxn, ulyn, px_w, px_h]
    mask = ones(clip.shape)

    # Loop trough the cells
    for i, j in product(range(px_w), range(px_h)):
        if not intersect_cell(geom, plx + (dx * i), ply + (dy * j), dx, dy):
            mask[j, i] = 0

    return clip[mask == 1]


def clip_weighted(
    ft: ogr.Feature,
    band: Grid,
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
[GeomSource](/api/GeomSource.qmd).
    band : Grid
        An object that contains a connection the band within the dataset. For further
        information, see [Grid](/api/Grid.qmd)!
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
    mask = ones((px_h * upscale, px_w * upscale))

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
    band: Grid,
    gtf: tuple,
) -> ndarray:
    """Pin a the value of a cell based on a coordinate.

    Parameters
    ----------
    point : tuple
        x and y coordinate.
    band : Grid
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
    yn = int(0 <= y <= oh)

    value = band[x, y, xn, yn]
    mask = ones(value.shape)  # This really is a dummy mask, but makes my life easy

    return value[mask == 1]
