"""Combined vector and raster methods for FIAT."""

from numpy import array
from osgeo import gdal, ogr, osr

from fiat.gis.util import pixel2world, world2pixel
from fiat.io import Grid


def clip(
    band: Grid,
    srs: osr.SpatialReference,
    gtf: tuple,
    ft: ogr.Feature,
):
    """Clip a grid based on a feature (vector).

    Parameters
    ----------
    band : Grid
        An object that contains a connection the band within the dataset. For further
        information, see [Grid](/api/Grid.qmd)!
    srs : osr.SpatialReference
        Spatial reference (Projection) of the Grid object (e.g. WGS84).
        Can be optained with the \
[get_srs](/api/GridSource/get_srs.qmd) method.
    gtf : tuple
        The geotransform of a grid dataset.
        Can be optained via the [get_geotransform]\
(/api/GridSource/get_geotransform.qmd) method.
        Has the following shape: (left, xres, xrot, upper, yrot, yres).
    ft : ogr.Feature
        A Feature according to the \
[ogr module](https://gdal.org/api/python/osgeo.ogr.html) of osgeo.
        Can be optained by indexing a \
[GeomSource](/api/GeomSource.qmd).

    Returns
    -------
    array
        A 1D array containing the clipped values.

    See Also
    --------
    - [clip_weighted](/api/overlay/clip_weighted.qmd)
    """
    geom = ft.GetGeometryRef()

    minX, maxX, minY, maxY = geom.GetEnvelope()
    ulX, ulY = world2pixel(gtf, minX, maxY)
    lrX, lrY = world2pixel(gtf, maxX, minY)
    c = pixel2world(gtf, ulX, ulY)
    new_gtf = (c[0], gtf[1], 0.0, c[1], 0.0, gtf[-1])
    pxWidth = int(lrX - ulX) + 1
    pxHeight = int(lrY - ulY) + 1

    clip = band[ulX, ulY, pxWidth, pxHeight]
    # m = mask.ReadAsArray(ulX,ulY,pxWidth,pxHeight)

    # pts = geom.GetGeometryRef(0)
    # pixels = [None] * pts.GetPointCount()
    # for p in range(pts.GetPointCount()):
    #     pixels[p] = (world2Pixel(gtf, pts.GetX(p), pts.GetY(p)))

    dr_r = gdal.GetDriverByName("MEM")
    b_r = dr_r.Create("memset", pxWidth, pxHeight, 1, gdal.GDT_Int16)
    b_r.SetSpatialRef(srs)
    b_r.SetGeoTransform(new_gtf)

    dr_g = ogr.GetDriverByName("Memory")
    src_g = dr_g.CreateDataSource("memdata")
    lay_g = src_g.CreateLayer("mem", srs)
    lay_g.CreateFeature(ft)

    gdal.RasterizeLayer(b_r, [1], lay_g, None, None, [1], ["ALL_TOUCHED=TRUE"])
    clip = clip[b_r.ReadAsArray() == 1]

    b_r = None
    dr_r = None
    lay_g = None
    src_g = None
    dr_g = None

    return clip


def clip_weighted(
    band: gdal.Band,
    srs: osr.SpatialReference,
    gtf: tuple,
    ft: ogr.Feature,
    upscale: int = 1,
):
    """Clip a grid based on a feature (vector), but weighted.

    This method caters to those who wish to have information about the percentages of \
cells that are touched by the feature.

    Warning!
    --------
    A high upscale value comes with a calculation penalty!

    Parameters
    ----------
    band : Grid
        An object that contains a connection the band within the dataset. For further
        information, see [Grid](/api/Grid.qmd)!
    srs : osr.SpatialReference
        Spatial reference (Projection) of the Grid object (e.g. WGS84).
        Can be optained with the \
[get_srs](/api/GridSource/get_srs.qmd) method.
    gtf : tuple
        The geotransform of a grid dataset.
        Can be optained via the [get_geotransform]\
(/api/GridSource/get_geotransform.qmd) method.
        Has the following shape: (left, xres, xrot, upper, yrot, yres).
    ft : ogr.Feature
        A Feature according to the \
[ogr module](https://gdal.org/api/python/osgeo.ogr.html) of osgeo.
        Can be optained by indexing a \
[GeomSource](/api/GeomSource.qmd).
    upscale : int
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

    minX, maxX, minY, maxY = geom.GetEnvelope()
    ulX, ulY = world2pixel(gtf, minX, maxY)
    lrX, lrY = world2pixel(gtf, maxX, minY)
    c = pixel2world(gtf, ulX, ulY)
    new_gtf = (c[0], gtf[1] / upscale, 0.0, c[1], 0.0, gtf[-1] / upscale)
    pxWidth = int(lrX - ulX) + 1
    pxHeight = int(lrY - ulY) + 1

    clip = band.ReadAsArray(ulX, ulY, pxWidth, pxHeight)
    # m = mask.ReadAsArray(ulX,ulY,pxWidth,pxHeight)

    # pts = geom.GetGeometryRef(0)
    # pixels = [None] * pts.GetPointCount()
    # for p in range(pts.GetPointCount()):
    #     pixels[p] = (world2Pixel(gtf, pts.GetX(p), pts.GetY(p)))

    dr_r = gdal.GetDriverByName("MEM")
    b_r = dr_r.Create(
        "memset", pxWidth * upscale, pxHeight * upscale, 1, gdal.GDT_Int16
    )
    b_r.SetSpatialRef(srs)
    b_r.SetGeoTransform(new_gtf)

    dr_g = ogr.GetDriverByName("Memory")
    src_g = dr_g.CreateDataSource("memdata")
    lay_g = src_g.CreateLayer("mem", srs)
    lay_g.CreateFeature(ft)

    gdal.RasterizeLayer(b_r, [1], lay_g, None, None, [1], ["ALL_TOUCHED=TRUE"])
    _w = b_r.ReadAsArray().reshape((pxHeight, upscale, pxWidth, -1)).mean(3).mean(1)
    clip = clip[_w != 0]

    b_r = None
    dr_r = None
    lay_g = None
    src_g = None
    dr_g = None

    return clip, _w


def mask(
    driver: str,
):
    """_summary_."""
    pass


def pin(
    band: Grid,
    gtf: tuple,
    point: tuple,
) -> array:
    """Pin a the value of a cell based on a coordinate.

    Parameters
    ----------
    band : Grid
        Input object. This holds a connection to the specified band.
    gtf : tuple
        The geotransform of a grid dataset.
        Can be optained via the [get_geotransform]\
(/api/GridSource/get_geotransform.qmd) method.
        Has the following shape: (left, xres, xrot, upper, yrot, yres).
    point : tuple
        x and y coordinate.

    Returns
    -------
    array
        A NumPy array containing one value.
    """
    X, Y = world2pixel(gtf, *point)

    value = band[X, Y, 1, 1]

    return value[0]
