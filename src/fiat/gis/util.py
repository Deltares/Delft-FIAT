"""Util of GIS module."""


def world2pixel(
    gtf: tuple,
    x: float | int,
    y: float | int,
):
    """Calculate the pixel location based on coordinates.

    (Thanks to the [ogr cookbook]\
(https://pcjericks.github.io/py-gdalogr-cookbook/index.html)!)

    Parameters
    ----------
    gtf : tuple
        The geotransform of a grid dataset.
        Can be optained via the [get_geotransform]\
(/api/GridSource/get_geotransform.qmd) method.
        Has the following shape: (left, xres, xrot, upper, yrot, yres).
    x : float | int
        The x coordinates of a point
    y : float | int
        The y coordinates of a point

    Returns
    -------
    tuple
        Row and column indices.

    Example
    -------
    ```Python
    # Load a dataset
    gs = fiat.io.GridSource(<some raster file>)
    # Get the geotransform
    gtf = gs.get_geotransform()
    # Calculate the indices
    row, col = world2pixel(gtf, <x>, <y>)
    ```
    """
    ulX = gtf[0]
    ulY = gtf[3]
    xDist = gtf[1]
    pixel = int((x - ulX) / xDist)
    line = int((ulY - y) / xDist)
    return (pixel, line)


def pixel2world(
    gtf: tuple,
    x: int,
    y: int,
):
    """Calculate coordinates based on pixel location.

    (Thanks to the [ogr cookbook]\
(https://pcjericks.github.io/py-gdalogr-cookbook/index.html)!)

    Parameters
    ----------
    gtf : tuple
        The geotransform of a grid dataset.
        Can be optained via the [get_geotransform]\
(/api/GridSource/get_geotransform.qmd) method.
        Has the following shape: (left, xres, xrot, upper, yrot, yres).
    x : int
        Column number of the pixel
    y : int
        Row number of the pixel

    Returns
    -------
    tuple
        Return the x, y coordinates of the upper left corner of the cell.

    Example
    -------
    ```Python
    # Load a dataset
    gs = fiat.io.GridSource(<some raster file>)
    # Get the geotransform
    gtf = gs.get_geotransform()
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
