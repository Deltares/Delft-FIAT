"""Combined vector and raster methods for FIAT."""

from itertools import product

from numpy import ndarray, ones
from osgeo import ogr

from fiat.gis.util import pixel2world, world2pixel
from fiat.io import Grid


def intersect_cell(
    geom: ogr.Geometry,
    x: float | int,
    y: float | int,
    dx: float | int,
    dy: float | int,
):
    """_summary_.

    _extended_summary_

    Parameters
    ----------
    geom : ogr.Geometry
        _description_
    x : float | int
        _description_
    y : float | int
        _description_
    dx : float | int
        _description_
    dy : float | int
        _description_
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
        Can be optained via the [get_geotransform]\
(/api/GridSource/get_geotransform.qmd) method.
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

    # Extract information
    dx = gtf[1]
    dy = gtf[5]
    minX, maxX, minY, maxY = geom.GetEnvelope()
    ulX, ulY = world2pixel(gtf, minX, maxY)
    lrX, lrY = world2pixel(gtf, maxX, minY)
    plX, plY = pixel2world(gtf, ulX, ulY)
    pxWidth = int(lrX - ulX) + 1
    pxHeight = int(lrY - ulY) + 1
    clip = band[ulX, ulY, pxWidth, pxHeight]
    mask = ones(clip.shape)

    # Loop trough the cells
    for i, j in product(range(pxWidth), range(pxHeight)):
        if not intersect_cell(geom, plX + (dx * i), plY + (dy * j), dx, dy):
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
        Can be optained via the [get_geotransform]\
(/api/GridSource/get_geotransform.qmd) method.
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
    minX, maxX, minY, maxY = geom.GetEnvelope()
    ulX, ulY = world2pixel(gtf, minX, maxY)
    lrX, lrY = world2pixel(gtf, maxX, minY)
    plX, plY = pixel2world(gtf, ulX, ulY)
    dxn = dx / upscale
    dyn = dy / upscale
    pxWidth = int(lrX - ulX) + 1
    pxHeight = int(lrY - ulY) + 1
    clip = band[ulX, ulY, pxWidth, pxHeight]
    mask = ones((pxHeight * upscale, pxWidth * upscale))

    # Loop trough the cells
    for i, j in product(range(pxWidth * upscale), range(pxHeight * upscale)):
        if not intersect_cell(geom, plX + (dxn * i), plY + (dyn * j), dxn, dyn):
            mask[j, i] = 0

    # Resample the higher resolution mask
    mask = mask.reshape((pxHeight, upscale, pxWidth, -1)).mean(3).mean(1)
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
        Can be optained via the [get_geotransform]\
(/api/GridSource/get_geotransform.qmd) method.
        Has the following shape: (left, xres, xrot, upper, yrot, yres).

    Returns
    -------
    ndarray
        A NumPy array containing one value.
    """
    x, y = world2pixel(gtf, *point)

    value = band[x, y, 1, 1]

    return value[0]
