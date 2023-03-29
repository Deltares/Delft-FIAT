from delft_fiat.gis.util import world2Pixel, Pixel2world

from osgeo import gdal, ogr


def clip(
    src: gdal.Dataset,
    band: gdal.Band,
    ft: ogr.Feature,
) -> "numpy.array":
    """_summary_

    Parameters
    ----------
    src : gdal.Dataset
        _description_
    band : gdal.Band
        _description_
    ft : ogr.Feature
        _description_

    Returns
    -------
    numpy.array
        _description_
    """

    gtf = src.GetGeoTransform()
    geom = ft.GetGeometryRef()

    minX, maxX, minY, maxY = geom.GetEnvelope()
    ulX, ulY = world2Pixel(gtf, minX, maxY)
    lrX, lrY = world2Pixel(gtf, maxX, minY)
    c = Pixel2world(gtf, ulX, ulY)
    new_gtf = (c[0], gtf[1], 0.0, c[1], 0.0, gtf[-1])
    pxWidth = int(lrX - ulX) + 1
    pxHeight = int(lrY - ulY) + 1

    clip = band.ReadAsArray(ulX, ulY, pxWidth, pxHeight)
    # m = mask.ReadAsArray(ulX,ulY,pxWidth,pxHeight)

    # pts = geom.GetGeometryRef(0)
    # pixels = [None] * pts.GetPointCount()
    # for p in range(pts.GetPointCount()):
    #     pixels[p] = (world2Pixel(gtf, pts.GetX(p), pts.GetY(p)))

    dr_r = gdal.GetDriverByName("MEM")
    b_r = dr_r.Create("memset", pxWidth, pxHeight, 1, gdal.GDT_Int16)
    b_r.SetSpatialRef(src.GetSpatialRef())
    b_r.SetGeoTransform(new_gtf)

    dr_g = ogr.GetDriverByName("Memory")
    src_g = dr_g.CreateDataSource("memdata")
    lay_g = src_g.CreateLayer("mem", src.GetSpatialRef())
    lay_g.CreateFeature(ft)

    gdal.RasterizeLayer(b_r, [1], lay_g, None, None, [1], ["ALL_TOUCHED=TRUE"])
    clip = clip[b_r.ReadAsArray() == 1]

    b_r = None
    dr_r = None
    lay_g = None
    src_g = None
    dr_g = None

    return clip


def mask(
    driver: str,
):
    pass


def pin(
    src: gdal.Band,
    band: gdal.Band,
    point: tuple,
) -> "numpy.array":
    """_summary_

    Parameters
    ----------
    src : gdal.Band
        _description_
    band : gdal.Band
        _description_
    point : tuple
        _description_

    Returns
    -------
    numpy.array
        _description_
    """

    gtf = src.GetGeoTransform()

    X, Y = world2Pixel(gtf, *point)

    value = band.ReadAsArray(X, Y, 1, 1)

    return value[0]
