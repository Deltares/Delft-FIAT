from delft_fiat.log import Log

import gc
import math
import os
import tomli_w
from itertools import product
from numpy import arange, random, zeros, float32
from osgeo import gdal, ogr
from osgeo import osr
from pathlib import Path

p = Path(__file__).parent

folders = (
    "exposure",
    "hazard",
    "vulnerability",
)


def create_dbase_stucture():
    for f in folders:
        if not Path(p, f).exists():
            os.mkdir(Path(p, f))


def create_exposure_dbase():
    with open(Path(p, "exposure", "spatial.csv"), "w") as f:
        f.write("Object ID,Extraction Method,Ground Floor Height,Ground Elevation,")
        f.write("Damage Function: Structure,Max Potential Damage: Structure\n")
        for n in range(5):
            if (n + 1) % 2 != 0:
                dmc = "struct_1"
            else:
                dmc = "struct_2"
            f.write(f"{n+1},area,0,0,{dmc},{(n+1)*1000}\n")


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
        "Object ID",
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
        ft.SetField("Object ID", idx + 1)
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


def create_exposure_geoms_2():
    geoms = (
        "POLYGON ((4.375 52.025, 4.385 52.025, 4.385 52.015, 4.375 52.015, 4.375 52.025))",
    )
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    dr = ogr.GetDriverByName("GPKG")
    src = dr.CreateDataSource(str(Path(p, "exposure", "spatial2.gpkg")))
    layer = src.CreateLayer(
        "spatial",
        srs,
        3,
    )

    field = ogr.FieldDefn(
        "Object ID",
        ogr.OFTInteger,
    )
    layer.CreateField(field)

    field = ogr.FieldDefn(
        "ObjectName",
        ogr.OFTString,
    )
    field.SetWidth(50)
    layer.CreateField(field)

    geom = ogr.CreateGeometryFromWkt(geoms[0])
    ft = ogr.Feature(layer.GetLayerDefn())
    ft.SetField("Object ID", 5)
    ft.SetField("ObjectName", f"fp_{5}")
    ft.SetGeometry(geom)

    layer.CreateFeature(ft)

    srs = None
    field = None
    geom = None
    ft = None
    layer = None
    src = None
    dr = None


def create_exposure_geoms_3():
    geoms = (
        "POLYGON ((4.375 52.025, 4.385 52.025, 4.385 52.015, 4.375 52.015, 4.375 52.025))",
        "POLYGON ((4.425 51.975, 4.435 51.975, 4.435 51.965, 4.425 51.965, 4.425 51.975))",
    )
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    dr = ogr.GetDriverByName("GPKG")
    src = dr.CreateDataSource(str(Path(p, "exposure", "spatial_missing.gpkg")))
    layer = src.CreateLayer(
        "spatial",
        srs,
        3,
    )

    field = ogr.FieldDefn(
        "Object ID",
        ogr.OFTInteger,
    )
    layer.CreateField(field)

    field = ogr.FieldDefn(
        "ObjectName",
        ogr.OFTString,
    )
    field.SetWidth(50)
    layer.CreateField(field)

    geom = ogr.CreateGeometryFromWkt(geoms[0])
    ft = ogr.Feature(layer.GetLayerDefn())
    ft.SetField("Object ID", 5)
    ft.SetField("ObjectName", f"fp_{5}")
    ft.SetGeometry(geom)

    layer.CreateFeature(ft)
    geom = None
    ft = None

    geom = ogr.CreateGeometryFromWkt(geoms[1])
    ft = ogr.Feature(layer.GetLayerDefn())
    ft.SetField("Object ID", 6)
    ft.SetField("ObjectName", f"fp_{6}")
    ft.SetGeometry(geom)

    layer.CreateFeature(ft)

    srs = None
    field = None
    geom = None
    ft = None
    layer = None
    src = None
    dr = None


def create_exposure_grid():
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    dr = gdal.GetDriverByName("netCDF")
    src = dr.Create(
        str(Path(p, "exposure", "spatial.nc")),
        10,
        10,
        1,
        gdal.GDT_Float32,
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
        data[x, y] = 2000 + ((x + y) * 100)
    band.WriteArray(data)

    band.FlushCache()
    src.FlushCache()

    srs = None
    band = None
    src = None
    dr = None


def create_hazard_map():
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    dr = gdal.GetDriverByName("netCDF")
    src = dr.Create(
        str(Path(p, "hazard", "event_map.nc")),
        10,
        10,
        1,
        gdal.GDT_Float32,
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


def create_risk_map():
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    dr = gdal.GetDriverByName("netCDF")
    src = dr.Create(
        str(Path(p, "hazard", "risk_map.nc")),
        10,
        10,
        4,
        gdal.GDT_Float32,
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

    for idx, fc in enumerate((1.5, 1.8, 1.9, 1.95)):
        band = src.GetRasterBand(idx + 1)
        data = zeros((10, 10))
        oneD = tuple(range(10))
        for x, y in product(oneD, oneD):
            data[x, y] = 3.6 - ((x + y) * 0.2)
        data *= fc
        band.WriteArray(data)
        band.FlushCache()
        band = None

    src.FlushCache()

    srs = None
    src = None
    dr = None


def create_settings():
    doc = {
        "global": {
            "crs": "EPSG:4326",
            "keep_temp_files": True,
        },
        "output": {
            "path": "output/event",
            "csv": {
                "name": "output.csv",
            },
            "geom": {"name1": "spatial.gpkg"},
        },
        "hazard": {
            "file": "hazard/event_map.nc",
            "crs": "EPSG:4326",
            "risk": False,
            "elevation_reference": "DEM",
        },
        "exposure": {
            "grid": {
                "file": "exposure/spatial.nc",
                "crs": "EPSG:4326",
            },
            "geom": {
                "file1": "exposure/spatial.gpkg",
                "csv": "exposure/spatial.csv",
                "crs": "EPSG:4326",
            },
        },
        "vulnerability": {
            "file": "vulnerability/vulnerability_curves.csv",
            "step_size": 0.01,
        },
        "categorical_bins": {
            "low": 0.25,
            "medium-low": 0.5,
            "medium-high": 0.75,
            "high": 1,
        },
    }

    with open(Path(p, "settings.toml"), "wb") as f:
        tomli_w.dump(doc, f)

    doc["output"]["path"] = "output/event_2g"
    doc["output"]["geom"]["name2"] = "spatial2.gpkg"
    doc["exposure"]["geom"]["file2"] = "exposure/spatial2.gpkg"

    with open(Path(p, "settings_2g.toml"), "wb") as f:
        tomli_w.dump(doc, f)

    doc["output"]["path"] = "output/event_missing"
    del doc["output"]["geom"]["name2"]
    del doc["exposure"]["geom"]["file2"]
    doc["output"]["geom"]["name1"] = "spatial_missing.gpkg"
    doc["exposure"]["geom"]["file1"] = "exposure/spatial_missing.gpkg"

    with open(Path(p, "settings_missing.toml"), "wb") as f:
        tomli_w.dump(doc, f)


def create_settings_risk():
    doc = {
        "global": {
            "crs": "EPSG:4326",
            "keep_temp_files": True,
        },
        "output": {
            "path": "output/risk",
            "csv": {
                "name": "output.csv",
            },
            "geom": {"name1": "spatial.gpkg"},
        },
        "hazard": {
            "file": "hazard/risk_map.nc",
            "crs": "EPSG:4326",
            "elevation_reference": "DEM",
            "risk": True,
            "return_periods": [2, 5, 10, 25],
            "settings": {
                "subset": "",
                "var_as_band": True,
            },
        },
        "exposure": {
            "grid": {
                "file": "exposure/spatial.nc",
                "crs": "EPSG:4326",
            },
            "geom": {
                "file1": "exposure/spatial.gpkg",
                "csv": "exposure/spatial.csv",
                "crs": "EPSG:4326",
            },
        },
        "vulnerability": {
            "file": "vulnerability/vulnerability_curves.csv",
            "step_size": 0.01,
        },
        "categorical_bins": {
            "low": 0.25,
            "medium-low": 0.5,
            "medium-high": 0.75,
            "high": 1,
        },
    }

    with open(Path(p, "settings_risk.toml"), "wb") as f:
        tomli_w.dump(doc, f)

    doc["output"]["path"] = "output/risk_2g"
    doc["output"]["geom"]["name2"] = "spatial2.gpkg"
    doc["exposure"]["geom"]["file2"] = "exposure/spatial2.gpkg"

    with open(Path(p, "settings_risk_2g.toml"), "wb") as f:
        tomli_w.dump(doc, f)


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
    create_exposure_geoms_2()
    create_exposure_geoms_3()
    create_exposure_grid()
    create_hazard_map()
    create_risk_map()
    create_settings()
    create_settings_risk()
    create_vulnerability()
    gc.collect()
    pass
