from delft_fiat.gis.util import world2pixel, pixel2world

from osgeo import gdal, ogr


def clip(
    band: gdal.Band,
    srs: "osr.SpatialReference",
    gtf: tuple,
    ft: ogr.Feature,
) -> "numpy.array":
    """Clip a raster based on a geometry feature and return the clipped array

    Parameters
    ----------
    src : gdal.Dataset
        Spatial reference
    band : gdal.Band
        Single layer within the raster dataset
    ft : ogr.Feature
        Geometry feature in the vector dataset

    Returns
    -------
    numpy.array
        _description_
    """

    # Get the geometry
    geom = ft.GetGeometryRef()

    # Get the bounding box
    minX, maxX, minY, maxY = geom.GetEnvelope()
    ulX, ulY = world2pixel(gtf, minX, maxY)
    lrX, lrY = world2pixel(gtf, maxX, minY)
    c = pixel2world(gtf, ulX, ulY)
    new_gtf = (c[0], gtf[1], 0.0, c[1], 0.0, gtf[-1])

    # Get the pixel size
    pxWidth = int(lrX - ulX) + 1
    pxHeight = int(lrY - ulY) + 1

    # Read the array
    clip = band.ReadAsArray(ulX, ulY, pxWidth, pxHeight)
    # m = mask.ReadAsArray(ulX,ulY,pxWidth,pxHeight)

    # pts = geom.GetGeometryRef(0)
    # pixels = [None] * pts.GetPointCount()
    # for p in range(pts.GetPointCount()):
    #     pixels[p] = (world2Pixel(gtf, pts.GetX(p), pts.GetY(p)))

    # Create the mask
    dr_r = gdal.GetDriverByName("MEM")
    b_r = dr_r.Create("memset", pxWidth, pxHeight, 1, gdal.GDT_Int16)

    # Set the spatial reference
    b_r.SetSpatialRef(srs)
    b_r.SetGeoTransform(new_gtf)

    # Create the layer
    dr_g = ogr.GetDriverByName("Memory")
    src_g = dr_g.CreateDataSource("memdata")
    lay_g = src_g.CreateLayer("mem", srs)
    lay_g.CreateFeature(ft)

    # Rasterize the layer
    gdal.RasterizeLayer(b_r, [1], lay_g, None, None, [1], ["ALL_TOUCHED=TRUE"])
    clip = clip[b_r.ReadAsArray() == 1]

    # Clean up
    b_r = None
    dr_r = None
    lay_g = None
    src_g = None
    dr_g = None

    # Return the clipped array
    return clip


def clip_weighted(
    band: gdal.Band,
    srs: "osr.SpatialReference",
    gtf: tuple,
    ft: ogr.Feature,
    upscale: int = 1,
) -> "numpy.array":
    """Clip a raster based on a geometry feature and return the weighted clipped array

    Parameters
    ----------
    src : gdal.Dataset
        Spatial reference
    band : gdal.Band
        Single layer within the raster dataset
    ft : ogr.Feature
        Geometry feature in the vector dataset
    upscale : int, optional
        scale factor for the weighted average, by default 1

    Returns
    -------
    numpy.array
        _description_
    """

    # Get the geometry
    geom = ft.GetGeometryRef()

    # Get the bounding box
    minX, maxX, minY, maxY = geom.GetEnvelope()
    ulX, ulY = world2pixel(gtf, minX, maxY)
    lrX, lrY = world2pixel(gtf, maxX, minY)
    c = pixel2world(gtf, ulX, ulY)
    new_gtf = (c[0], gtf[1] / upscale, 0.0, c[1], 0.0, gtf[-1] / upscale)

    # Get the pixel size
    pxWidth = int(lrX - ulX) + 1
    pxHeight = int(lrY - ulY) + 1

    # Read the array
    clip = band.ReadAsArray(ulX, ulY, pxWidth, pxHeight)
    # m = mask.ReadAsArray(ulX,ulY,pxWidth,pxHeight)

    # pts = geom.GetGeometryRef(0)
    # pixels = [None] * pts.GetPointCount()
    # for p in range(pts.GetPointCount()):
    #     pixels[p] = (world2Pixel(gtf, pts.GetX(p), pts.GetY(p)))

    # Create the mask
    dr_r = gdal.GetDriverByName("MEM")
    b_r = dr_r.Create(
        "memset", pxWidth * upscale, pxHeight * upscale, 1, gdal.GDT_Int16
    )

    # Set the spatial reference
    b_r.SetSpatialRef(srs)
    b_r.SetGeoTransform(new_gtf)

    # Create the layer
    dr_g = ogr.GetDriverByName("Memory")
    src_g = dr_g.CreateDataSource("memdata")
    lay_g = src_g.CreateLayer("mem", srs)
    lay_g.CreateFeature(ft)

    # Rasterize the layer
    gdal.RasterizeLayer(b_r, [1], lay_g, None, None, [1], ["ALL_TOUCHED=TRUE"])
    _w = b_r.ReadAsArray().reshape((pxHeight, upscale, pxWidth, -1)).mean(3).mean(1)
    clip = clip[_w != 0]

    # Clean up
    b_r = None
    dr_r = None
    lay_g = None
    src_g = None
    dr_g = None

    # Return the clipped array
    return clip, _w


def mask(
    driver: str,
):
    pass


def pin(
    band: gdal.Band,
    gtf: tuple,
    point: tuple,
) -> "numpy.array":
    """Get the value of a raster at a specific point

    Parameters
    ----------
    src : gdal.Dataset
        Spatial reference
    band : gdal.Band
        Single layer within the raster dataset
    point : tuple
        Coordinate of the point

    Returns
    -------
    numpy.array
        _description_
    """

    # Get the pixel location
    X, Y = world2pixel(gtf, *point)

    # Read the array
    value = band.ReadAsArray(X, Y, 1, 1)

    # Return the value
    return value[0]
