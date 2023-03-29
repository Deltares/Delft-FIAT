from delft_fiat.log import Log

import gc
import math
import os
from itertools import product
from numpy import arange, random, zeros
from osgeo import gdal, ogr
from osgeo import osr
from pathlib import Path

p = Path(__file__).parent

folders = (
    "exposure",
    "hazard",
    "run_default",
    "vulnerability",
)


def create_dbase_stucture():
    for f in folders:
        if not Path(p, f).exists():
            os.mkdir(Path(p, f))


def create_exposure_geoms():
    geoms = (
        "POLYGON ((4.355 52.045, 4.355 52.035, 4.365 52.035, 4.365 52.045, 4.355 52.045))",
        "POLYGON ((4.395 52.005, 4.395 51.975, 4.415 51.975, 4.415 51.985, 4.405 51.985, 4.405 52.005, 4.395 52.005))",
        "POLYGON ((4.365 51.960, 4.375 51.990, 4.385 51.960, 4.365 51.960))",
        "POLYGON ((4.410 52.030, 4.440 52.030, 4.435 52.010, 4.415 52.010, 4.410 52.030))",
    )
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    dr = ogr.GetDriverByName("GPKG")
    src = dr.CreateDataSource(str(Path(p, "exposure", "spatial.gpkg")))
    layer = src.CreateLayer(
        "spatial",
        srs,
        3,
    )

    field = ogr.FieldDefn(
        "Object_ID",
        ogr.OFTInteger,
    )
    layer.CreateField(field)

    field = ogr.FieldDefn(
        "ObjectName",
        ogr.OFTString,
    )
    field.SetWidth(50)
    layer.CreateField(field)

    for idx, geom in enumerate(geoms):
        geom = ogr.CreateGeometryFromWkt(geom)
        ft = ogr.Feature(layer.GetLayerDefn())
        ft.SetField("Object_ID", idx + 1)
        ft.SetField("ObjectName", f"fp_{idx+1}")
        ft.SetGeometry(geom)

        layer.CreateFeature(ft)

    srs = None
    field = None
    geom = None
    ft = None
    layer = None
    src = None
    dr = None


def create_exposure_dbase():
    with open(Path(p, "exposure", "spatial.csv"), "w") as f:
        f.write("Object ID,Extraction Method,Ground Floor Height,")
        f.write("Damage Function: struct,Max Potential Damage: struct\n")
        for n in range(4):
            if (n + 1) % 2 != 0:
                dmc = "struct_1"
            else:
                dmc = "struct_2"
            f.write(f"{n+1},area,0,{dmc},{(n+1)*1000}\n")


def create_hazard_map():
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    dr = gdal.GetDriverByName("netCDF")
    src = dr.Create(
        str(Path(p, "hazard", "event_map.nc")),
        10,
        10,
        1,
        gdal.GFT_Real,
    )
    gtf = (
        4.35,
        0.01,
        0.0,
        52.05,
        0.0,
        -0.01,
    )
    src.SetSpatialRef(srs)
    src.SetGeoTransform(gtf)

    band = src.GetRasterBand(1)
    data = zeros((10, 10))
    oneD = tuple(range(10))
    for x, y in product(oneD, oneD):
        data[x, y] = 3.6 - ((x + y) * 0.2)
    band.WriteArray(data)

    band.FlushCache()
    src.FlushCache()

    srs = None
    band = None
    src = None
    dr = None


def create_vulnerability():
    def log_base(b, x):
        r = math.log(x) / math.log(b)
        if r < 0:
            return 0
        return r

    wd = arange(0, 5.25, 0.25)
    dc1 = [0.0] + [float(round(min(log_base(5, x), 0.96), 2)) for x in wd[1:]]
    dc2 = [0.0] + [float(round(min(log_base(3, x), 0.96), 2)) for x in wd[1:]]

    with open(Path(p, "vulnerability", "vulnerability_curves.csv"), mode="w") as f:
        f.write("#UNIT=meter\n")
        f.write("#method,mean,max\n")
        f.write("water depth,struct_1,struct_2\n")
        for idx, item in enumerate(wd):
            f.write(f"{item},{dc1[idx]},{dc2[idx]}\n")


if __name__ == "__main__":
    create_dbase_stucture()
    create_exposure_dbase()
    create_exposure_geoms()
    create_hazard_map()
    create_vulnerability()
    gc.collect()
    pass
