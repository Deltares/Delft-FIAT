"""Util of GIS module."""

from math import floor


def world2pixel(
    gtf: tuple[float, ...],
    x: float | int,
    y: float | int,
) -> tuple[int, int]:
    """Calculate the pixel location based on coordinates.

    (Thanks to the [ogr cookbook]\
(https://pcjericks.github.io/py-gdalogr-cookbook/index.html)!)

    Parameters
    ----------
    gtf : tuple
        The geotransform of a grid dataset.
        Has the following shape: (left, xres, xrot, upper, yrot, yres).
    x : float | int
        The x coordinates of a point
    y : float | int
        The y coordinates of a point

    Returns
    -------
    tuple[int]
        Row and column indices.

    Examples
    --------
    ```Python
    # Load a dataset
    gs = fiat.driver.NetcdfReader(<some raster file>)
    # Get the geotransform
    gtf = gs.geotransform
    # Calculate the indices
    row, col = world2pixel(gtf, <x>, <y>)
    ```
    """
    ulX = gtf[0]
    ulY = gtf[3]
    xDist = gtf[1]
    yDist = gtf[5]
    coorX = floor((x - ulX) / xDist)
    coorY = floor((y - ulY) / yDist)
    return (coorX, coorY)


def pixel2world(
    gtf: tuple[float, ...],
    x: int,
    y: int,
) -> tuple[float, float]:
    """Calculate coordinates based on pixel location.

    (Thanks to the [ogr cookbook]\
(https://pcjericks.github.io/py-gdalogr-cookbook/index.html)!)

    Parameters
    ----------
    gtf : tuple
        The geotransform of a grid dataset.
        Has the following shape: (left, xres, xrot, upper, yrot, yres).
    x : int
        Column number of the pixel
    y : int
        Row number of the pixel

    Returns
    -------
    tuple[float]
        Return the x, y coordinates of the upper left corner of the cell.

    Examples
    --------
    ```Python
    # Load a dataset
    gs = fiat.driver.NetcdfReader(<some raster file>)
    # Get the geotransform
    gtf = gs.geotransform
    # Calculate the coordinates
    x, y = pixel2world(gtf, <column>, <row>)
    ```
    """
    ulX = gtf[0]
    ulY = gtf[3]
    xDist = gtf[1]
    yDist = gtf[5]
    coorX = ulX + (x * xDist)
    coorY = ulY + (y * yDist)
    return (coorX, coorY)


def subtransform_from_pixel(
    gtf: tuple[float, ...],
    ul: tuple[int, int],
    br: tuple[int, int],
) -> tuple[float, ...]:
    """Get the transform within the grid defined by a transform based on pixels.

    Parameters
    ----------
    gtf : tuple[float, ...]
        The total geotransform.
    ul : tuple[int, int]
        The upper left corner in indices.
    br : tuple[int, int]
        The bottom right corner in indices.

    Returns
    -------
    tuple[float, ...]
        The sub geotransform.
    """
    x, y = pixel2world(gtf, ul[0], ul[1])
    if gtf[5] > 0:
        _, y = pixel2world(gtf, br[0], br[1])
    return (x, gtf[1], gtf[2], y, gtf[4], gtf[5])
