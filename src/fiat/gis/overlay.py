"""Combined vector and raster methods for FIAT."""

from numpy import any, arange, array, ndarray, ones, stack, tile
from osgeo import ogr

from fiat.gis.rasterize import rasterize
from fiat.gis.util import pixel2world, world2pixel
from fiat.io import Grid


def vertices(
    mask,
    xmin,
    xmax,
    ymin,
    ymax,
    geometry,
):
    """_summary_."""
    px = geometry[:, 0]
    py = geometry[:, 1]
    mask |= any(
        (
            (px[:, None, None] > xmin)
            & (px[:, None, None] < xmax)
            & (py[:, None, None] > ymin)
            & (py[:, None, None] < ymax)
        ),
        axis=0,
    )
    return mask


def clip(
    ft: ogr.Feature,
    band: Grid,
    gtf: tuple,
    all_touched: bool = False,
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
    all_touched : bool, optional
        Whether or not to include cells that are 'touched' without covering the
        center of the cell.

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
    gtype = geom.GetGeometryType()
    gself = geom
    if gtype in [3, 6]:
        gself = geom.GetGeometryRef(0)

    # Extract information
    dx = gtf[1]
    dy = gtf[5]
    minX, maxX, minY, maxY = geom.GetEnvelope()
    ulX, ulY = world2pixel(gtf, minX, maxY)
    lrX, lrY = world2pixel(gtf, maxX, minY)
    plX, plY = pixel2world(gtf, ulX, ulY)
    pxWidth = int(lrX - ulX) + 1
    pxHeight = int(lrY - ulY) + 1

    # Create clip and mask
    clip = band[ulX, ulY, pxWidth, pxHeight]
    mask = ones((pxHeight, pxWidth))

    x = tile(arange(plX + 0.5 * dx, plX + (dx * pxWidth), dx), (pxHeight, 1))
    y = tile(arange(plY + 0.5 * dy, plY + (dy * pxHeight), dy), (pxWidth, 1)).T
    # Create 3d arrays when all touched is true, to check for the corners
    if all_touched:
        x = stack([x - 0.5 * dx, x + 0.5 * dx, x + 0.5 * dx, x - 0.5 * dx])
        y = stack([y - 0.5 * dy, y - 0.5 * dy, y + 0.5 * dy, y + 0.5 * dy])

    if gtype > 3:
        geometry = gself.GetGeometryRef(0).GetPoints()
    else:
        geometry = gself.GetPoints()
    mask = rasterize(x, y, geometry)

    if all_touched:
        mask = any(mask, axis=0)
        # Get the vertex touched cells
        vertices(mask, x[0], x[1], y[2], y[0], array(geometry))

    return clip[mask == 1]


def clip_weighted(
    ft: ogr.Feature,
    band: Grid,
    gtf: tuple,
    all_touched: bool = False,
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
    all_touched : bool, optional
        Whether or not to include cells that are 'touched' without covering the
        center of the cell.
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
    gtype = geom.GetGeometryType()
    gself = geom
    if gtype in [3, 6]:
        gself = geom.GetGeometryRef(0)

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

    # Setup clip and mask arrays
    clip = band[ulX, ulY, pxWidth, pxHeight]
    x = tile(
        arange(plX + 0.5 * dxn, plX + (dxn * (pxWidth * upscale)), dxn),
        (pxHeight * upscale, 1),
    )
    y = tile(
        arange(plY + 0.5 * dyn, plY + (dyn * (pxHeight * upscale)), dyn),
        (pxWidth * upscale, 1),
    ).T
    if all_touched:
        x = stack([x - 0.5 * dxn, x + 0.5 * dxn, x + 0.5 * dxn, x - 0.5 * dxn])
        y = stack([y - 0.5 * dyn, y - 0.5 * dyn, y + 0.5 * dyn, y + 0.5 * dyn])

    if gtype > 3:
        geometry = gself.GetGeometryRef(0).GetPoints()
    else:
        geometry = gself.GetPoints()
    mask = rasterize(x, y, geometry)

    if all_touched:
        mask = any(mask, axis=0)
        # Get the vertex touched cells
        vertices(mask, x[0], x[1], y[2], y[0], array(geometry))

    # Resample the higher resolution mask
    mask = mask.reshape((pxHeight, upscale, pxWidth, -1)).mean(3).mean(1)
    clip = clip[mask != 0]

    return clip, mask


def mask(
    driver: str,
):
    """_summary_."""
    pass


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
