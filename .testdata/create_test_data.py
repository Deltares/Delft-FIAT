"""Create data to test with."""

import copy
import gc
import math
import os
from itertools import product
from pathlib import Path

import tomlkit
from numpy import arange, zeros
from osgeo import gdal, ogr, osr

p = Path(__file__).parent

folders = (
    "exposure",
    "hazard",
    "vulnerability",
)
osr.UseExceptions()


def create_dbase_stucture():
    """Create folder structure, very difficult, yes.."""
    for f in folders:
        if not Path(p, f).exists():
            os.mkdir(Path(p, f))


def create_exposure_dbase():
    """Create default exposure data for basic vector and the fifth."""
    with open(Path(p, "exposure", "spatial.csv"), "wb") as f:
        f.write(b"object_id,extract_method,ground_flht,ground_elevtn,")
        f.write(b"fn_damage_structure,max_damage_structure\n")
        for n in range(5):
            if (n + 1) % 2 != 0:
                dmc = "struct_1"
            else:
                dmc = "struct_2"
            f.write(f"{n+1},area,0,0,{dmc},{(n+1)*1000}\n".encode())


def create_exposure_dbase_missing():
    """Create exposure data with missing entry compared to vector."""
    with open(Path(p, "exposure", "spatial_missing.csv"), "w") as f:
        f.write("extract_method,ground_flht,ground_elevtn,")
        f.write("fn_damage_structure,max_damage_structure\n")
        for n in range(5):
            if (n + 1) % 2 != 0:
                dmc = "struct_1"
            else:
                dmc = "struct_2"
            f.write(f"area,0,0,{dmc},{(n+1)*1000}\n")


def create_exposure_dbase_partial():
    """Create exposure data for vector data that partially lies outside."""
    with open(Path(p, "exposure", "spatial_partial.csv"), "w") as f:
        f.write("object_id,extract_method,ground_flht,ground_elevtn,")
        f.write("fn_damage_structure,fn_damage_content,max_damage_structure\n")
        for n in range(5):
            if (n + 1) % 2 != 0:
                dmc = "struct_1"
            else:
                dmc = "struct_2"
            f.write(f"{n+1},area,0,0,{dmc},{dmc},{(n+1)*1000}\n")


def create_exposure_dbase_win():
    """Create exposure data with Windows newline char."""
    with open(Path(p, "exposure", "spatial_win.csv"), "wb") as f:
        f.write(b"object_id,extract_method,ground_flht,ground_elevtn,")
        f.write(b"fn_damage_structure,max_damage_structure\r\n")
        for n in range(5):
            if (n + 1) % 2 != 0:
                dmc = "struct_1"
            else:
                dmc = "struct_2"
            f.write(f"{n+1},area,0,0,{dmc},{(n+1)*1000}\r\n".encode())


def create_exposure_dbase_with_meta():
    """Create exposure data with metadata."""
    with open(Path(p, "exposure", "spatial_meta.csv"), "wb") as f:
        f.write(b"#version=v0.0.1\n")
        f.write(b"#foo,bar\n")
        f.write(b"#dtypes:int,str,int,int,str,float\n")
        f.write(b"object_id,extract_method,ground_flht,ground_elevtn,")
        f.write(b"fn_damage_structure,max_damage_structure\n")
        for n in range(5):
            if (n + 1) % 2 != 0:
                dmc = "struct_1"
            else:
                dmc = "struct_2"
            f.write(f"{n+1},area,0,0,{dmc},{(n+1)*1000}\n".encode())


def create_exposure_geoms(epsg=None):
    """Create basic vector file with 4 geometries."""
    geoms = (
        "POLYGON ((0.5 9.5, 0.5 8.5, 1.5 8.5, 1.5 9.5, 0.5 9.5))",
        "POLYGON ((4.5 5.5, 4.5 2.5, 6.5 2.5, 6.5 3.5, 5.5 3.5, 5.5 5.5, 4.5 5.5))",
        "POLYGON ((1.5 1.05, 2.5 3.95, 3.5 1.05, 1.5 1.05))",
        "POLYGON ((6.05 7.95, 8.95 7.95, 8.5 6.05, 6.5 6.05, 6.05 7.95))",
    )
    driver = "FlatGeoBuf"
    add = "_no_srs"
    suffix = ".fgb"
    srs = None
    if epsg is not None:
        driver = "GeoJSON"
        suffix = ".geojson"
        add = ""
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(epsg)

    dr = ogr.GetDriverByName(driver)
    src = dr.CreateDataSource(str(Path(p, "exposure", f"spatial{add}{suffix}")))
    layer = src.CreateLayer(
        f"spatial{add}",
        srs=srs,
        geom_type=3,
    )

    field = ogr.FieldDefn(
        "object_id",
        ogr.OFTInteger,
    )
    layer.CreateField(field)

    field = ogr.FieldDefn(
        "object_name",
        ogr.OFTString,
    )
    field.SetWidth(50)
    layer.CreateField(field)

    for idx, geom in enumerate(geoms):
        geom = ogr.CreateGeometryFromWkt(geom)
        ft = ogr.Feature(layer.GetLayerDefn())
        ft.SetField("object_id", idx + 1)
        ft.SetField("object_name", f"fp_{idx+1}")
        ft.SetGeometry(geom)

        layer.CreateFeature(ft)

    srs = None
    field = None
    geom = None
    ft = None
    layer = None
    src = None
    dr = None


def create_exposure_geoms_5th():
    """Create vector file with fifth geometry for calculation."""
    geoms = ("POLYGON ((2.5 7.5, 3.5 7.5, 3.5 6.5, 2.5 6.5, 2.5 7.5))",)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    dr = ogr.GetDriverByName("GeoJSON")
    src = dr.CreateDataSource(str(Path(p, "exposure", "spatial2.geojson")))
    layer = src.CreateLayer(
        "spatial2",
        srs,
        3,
    )

    field = ogr.FieldDefn(
        "object_id",
        ogr.OFTInteger,
    )
    layer.CreateField(field)

    field = ogr.FieldDefn(
        "object_name",
        ogr.OFTString,
    )
    field.SetWidth(50)
    layer.CreateField(field)

    geom = ogr.CreateGeometryFromWkt(geoms[0])
    ft = ogr.Feature(layer.GetLayerDefn())
    ft.SetField("object_id", 5)
    ft.SetField("object_name", f"fp_{5}")
    ft.SetGeometry(geom)

    layer.CreateFeature(ft)

    srs = None
    field = None
    geom = None
    ft = None
    layer = None
    src = None
    dr = None


def create_exposure_geoms_missing():
    """Create vector data with no data in exposure data csv."""
    geoms = (
        "POLYGON ((2.5 7.5, 3.5 7.5, 3.5 6.5, 2.5 6.5, 2.5 7.5))",
        "POLYGON ((7.5 2.5, 8.5 2.5, 8.5 1.5, 7.5 1.5, 7.5 2.5))",
    )
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    dr = ogr.GetDriverByName("GeoJSON")
    src = dr.CreateDataSource(str(Path(p, "exposure", "spatial_missing.geojson")))
    layer = src.CreateLayer(
        "spatial",
        srs,
        3,
    )

    field = ogr.FieldDefn(
        "object_id",
        ogr.OFTInteger,
    )
    layer.CreateField(field)

    field = ogr.FieldDefn(
        "object_name",
        ogr.OFTString,
    )
    field.SetWidth(50)
    layer.CreateField(field)

    geom = ogr.CreateGeometryFromWkt(geoms[0])
    ft = ogr.Feature(layer.GetLayerDefn())
    ft.SetField("object_id", 5)
    ft.SetField("object_name", f"fp_{5}")
    ft.SetGeometry(geom)

    layer.CreateFeature(ft)
    geom = None
    ft = None

    geom = ogr.CreateGeometryFromWkt(geoms[1])
    ft = ogr.Feature(layer.GetLayerDefn())
    ft.SetField("object_id", 6)
    ft.SetField("object_name", f"fp_{6}")
    ft.SetGeometry(geom)

    layer.CreateFeature(ft)

    srs = None
    field = None
    geom = None
    ft = None
    layer = None
    src = None
    dr = None


def create_exposure_geoms_outside():
    """Create vector data that lies outside of hazard."""
    geoms = (
        "POLYGON ((0.5 11.5, 0.5 10.5, 1.5 10.5, 1.5 11.5, 0.5 11.5))",
        "POLYGON ((4.5 10.5, 4.5 9.5, 5.5 9.5, 5.5 10.5, 4.5 10.5))",
        "POLYGON ((8.5 9.5, 8.5 8.5, 9.5 8.5, 9.5 9.5, 8.5 9.5))",
    )
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    dr = ogr.GetDriverByName("GeoJSON")
    src = dr.CreateDataSource(str(Path(p, "exposure", "spatial_outside.geojson")))
    layer = src.CreateLayer(
        "spatial",
        srs,
        3,
    )

    field = ogr.FieldDefn(
        "object_id",
        ogr.OFTInteger,
    )
    layer.CreateField(field)

    field = ogr.FieldDefn(
        "object_name",
        ogr.OFTString,
    )
    field.SetWidth(50)
    layer.CreateField(field)

    for idx, geom in enumerate(geoms):
        geom = ogr.CreateGeometryFromWkt(geom)
        ft = ogr.Feature(layer.GetLayerDefn())
        ft.SetField("object_id", idx + 1)
        ft.SetField("object_name", f"fp_{idx+1}")
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
    """Create raster file with exposure data for grid model."""
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
        0.0,
        1.0,
        0.0,
        10.0,
        0.0,
        -1.0,
    )
    src.SetSpatialRef(srs)
    src.SetGeoTransform(gtf)

    band = src.GetRasterBand(1)
    data = zeros((10, 10))
    oneD = tuple(range(10))
    for x, y in product(oneD, oneD):
        data[x, y] = 2000 + ((x + y) * 100)
    band.WriteArray(data)
    band.SetMetadataItem("fn_damage", "struct_1")

    band.FlushCache()
    src.FlushCache()

    srs = None
    band = None
    src = None
    dr = None


def create_hazard_event_map(epsg: int = None):
    """Create hazard event map."""
    add = "_no_srs"
    if epsg is not None:
        add = ""
    dr = gdal.GetDriverByName("netCDF")
    src = dr.Create(
        str(Path(p, "hazard", f"event_map{add}.nc")),
        10,
        10,
        1,
        gdal.GDT_Float32,
    )
    srs = None
    if epsg is not None:
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)
        src.SetSpatialRef(srs)
    gtf = (
        0.0,
        1.0,
        0.0,
        10.0,
        0.0,
        -1.0,
    )
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


def create_hazard_event_map_highres():
    """Create a high resolution hazard map to be reprojected."""
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    dr = gdal.GetDriverByName("netCDF")
    src = dr.Create(
        str(Path(p, "hazard", "event_map_highres.nc")),
        100,
        100,
        1,
        gdal.GDT_Float32,
    )
    gtf = (
        0.0,
        0.1,
        0.0,
        10.0,
        0.0,
        -0.1,
    )
    src.SetSpatialRef(srs)
    src.SetGeoTransform(gtf)

    band = src.GetRasterBand(1)
    data = zeros((100, 100))
    oneD = tuple(range(100))
    for x, y in product(oneD, oneD):
        data[x, y] = 3.6 - ((x + y) * 0.02)
    band.WriteArray(data)

    band.FlushCache()
    src.FlushCache()

    srs = None
    band = None
    src = None
    dr = None


def create_hazard_risk_map():
    """Create a hazard map for risk calculations."""
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
        0.0,
        1.0,
        0.0,
        10.0,
        0.0,
        -1.0,
    )
    src.SetSpatialRef(srs)
    src.SetGeoTransform(gtf)

    # Set return periods values
    rps = [2, 5, 10, 25]
    for idx, fc in enumerate((1.5, 1.8, 1.9, 1.95)):
        band = src.GetRasterBand(idx + 1)
        data = zeros((10, 10))
        oneD = tuple(range(10))
        for x, y in product(oneD, oneD):
            data[x, y] = 3.6 - ((x + y) * 0.2)
        data *= fc
        band.WriteArray(data)
        band.SetMetadataItem("return_period", f"{rps[idx]}")
        band.FlushCache()
        band = None

    src.FlushCache()

    srs = None
    src = None
    dr = None


def create_settings_geom():
    """Create exposure geometry model settings."""
    doc = {
        "model": {
            "model_type": "geom",
            "srs": {
                "value": "EPSG:4326",
            },
        },
        "output": {
            "path": "output/geom_event",
            "geom": [{"name": "spatial.gpkg"}],
        },
        "hazard": {
            "file": "hazard/event_map.nc",
            "elevation_reference": "DEM",
            "settings": {
                "srs": "EPSG:4326",
            },
        },
        "exposure": {
            "geom": [
                {
                    "file": "exposure/spatial.geojson",
                    "settings": {
                        "srs": "EPSG:4326",
                    },
                },
            ],
        },
        "vulnerability": {
            "file": "vulnerability/vulnerability_curves.csv",
            "step_size": 0.01,
        },
    }

    # Dump directly as default event toml
    with open(Path(p, "geom_event.toml"), "w") as f:
        tomlkit.dump(doc, f)

    # Setup toml with two geometry files
    doc2g = copy.deepcopy(doc)
    doc2g["output"]["path"] = "output/geom_event_2g"
    doc2g["output"]["geom"].append({"name": "spatial2.gpkg"})
    doc2g["exposure"]["geom"].append({"file": "exposure/spatial2.geojson"})

    with open(Path(p, "geom_event_2g.toml"), "w") as f:
        tomlkit.dump(doc2g, f)

    # Setup toml with missing geometry meta
    doc_m = copy.deepcopy(doc)
    doc_m["output"]["path"] = "output/geom_event_missing"
    doc_m["output"]["geom"][0]["name"] = "spatial_missing.gpkg"
    doc_m["exposure"]["geom"][0]["file"] = "exposure/spatial_missing.geojson"

    with open(Path(p, "geom_event_missing.toml"), "w") as f:
        tomlkit.dump(doc_m, f)

    # Setup toml with geometries lying outside hazard are
    doc_o = copy.deepcopy(doc)
    doc_o["exposure"]["geom"][0]["file"] = "exposure/spatial_outside.geojson"

    with open(Path(p, "geom_event_outside.toml"), "w") as f:
        tomlkit.dump(doc_o, f)

    # Setup toml for risk calculation
    doc_r = copy.deepcopy(doc)
    doc_r["model"]["risk"] = True
    doc_r["output"]["path"] = "output/geom_risk"
    doc_r["hazard"]["file"] = "hazard/risk_map.nc"
    doc_r["hazard"]["return_periods"] = [2, 5, 10, 25]
    doc_r["hazard"]["settings"].update({"var_as_band": True})

    with open(Path(p, "geom_risk.toml"), "w") as f:
        tomlkit.dump(doc_r, f)

    # Setup toml for risk calculation with 2 geometries
    doc_r2g = copy.deepcopy(doc_r)
    doc_r2g["output"]["path"] = "output/geom_risk_2g"
    doc_r2g["output"]["geom"].append({"name": "spatial2.gpkg"})
    doc_r2g["exposure"]["geom"].append({"file2": "exposure/spatial2.geojson"})

    with open(Path(p, "geom_risk_2g.toml"), "w") as f:
        tomlkit.dump(doc_r2g, f)


def create_settings_grid():
    """Create exposure grid model settings."""
    doc = {
        "model": {
            "model_type": "grid",
            "srs": {
                "value": "EPSG:4326",
            },
        },
        "output": {
            "path": "output/grid_event",
            "grid": {"name": "output.nc"},
        },
        "hazard": {
            "file": "hazard/event_map.nc",
            "risk": False,
            "elevation_reference": "DEM",
            "settings": {
                "srs": "EPSG:4326",
            },
        },
        "exposure": {
            "grid": {
                "file": "exposure/spatial.nc",
                "settings": {
                    "srs": "EPSG:4326",
                },
            },
        },
        "vulnerability": {
            "file": "vulnerability/vulnerability_curves.csv",
            "step_size": 0.01,
        },
    }

    with open(Path(p, "grid_event.toml"), "w") as f:
        tomlkit.dump(doc, f)

    doc_r = copy.deepcopy(doc)
    doc_r["model"]["risk"] = True
    doc_r["output"]["path"] = "output/grid_risk"
    doc_r["hazard"]["file"] = "hazard/risk_map.nc"
    doc_r["hazard"]["return_periods"] = [2, 5, 10, 25]
    doc_r["hazard"]["settings"].update({"var_as_band": True})

    with open(Path(p, "grid_risk.toml"), "w") as f:
        tomlkit.dump(doc_r, f)

    doc_u = copy.deepcopy(doc)
    doc_u["hazard"]["file"] = "hazard/event_map_highres.nc"

    with open(Path(p, "grid_unequal.toml"), "w") as f:
        tomlkit.dump(doc_u, f)


def create_vulnerability():
    """Create vulnerability curves."""

    def log_base(b, x):
        r = math.log(x) / math.log(b)
        if r < 0:
            return 0
        return r

    wd = arange(0, 5.25, 0.25)
    dc1 = [0.0] + [float(round(min(log_base(5, x), 0.96), 2)) for x in wd[1:]]
    dc2 = [0.0] + [float(round(min(log_base(3, x), 0.96), 2)) for x in wd[1:]]

    with open(Path(p, "vulnerability", "vulnerability_curves.csv"), mode="wb") as f:
        f.write(b"#UNIT=meter\n")
        f.write(b"#method,mean,max\n")
        f.write(b"water depth,struct_1,struct_2\n")
        for idx, item in enumerate(wd):
            f.write(f"{item},{dc1[idx]},{dc2[idx]}\n".encode())


def create_vulnerability_win():
    """Create vulnerability curves with Windows newline char."""

    def log_base(b, x):
        r = math.log(x) / math.log(b)
        if r < 0:
            return 0
        return r

    wd = arange(0, 5.25, 0.25)
    dc1 = [0.0] + [float(round(min(log_base(5, x), 0.96), 2)) for x in wd[1:]]
    dc2 = [0.0] + [float(round(min(log_base(3, x), 0.96), 2)) for x in wd[1:]]

    with open(Path(p, "vulnerability", "vulnerability_curves_win.csv"), mode="wb") as f:
        f.write(b"#UNIT=meter\r\n")
        f.write(b"#method,mean,max\r\n")
        f.write(b"water depth,struct_1,struct_2\r\n")
        for idx, item in enumerate(wd):
            f.write(f"{item},{dc1[idx]},{dc2[idx]}\r\n".encode())


if __name__ == "__main__":
    create_dbase_stucture()
    create_exposure_dbase()
    create_exposure_dbase_missing()
    create_exposure_dbase_partial()
    create_exposure_dbase_win()
    create_exposure_dbase_with_meta()
    create_exposure_geoms(epsg=4326)
    create_exposure_geoms(epsg=None)
    create_exposure_geoms_5th()
    create_exposure_geoms_missing()
    create_exposure_geoms_outside()
    create_exposure_grid()
    create_hazard_event_map(epsg=4326)
    create_hazard_event_map(epsg=None)
    create_hazard_event_map_highres()
    create_hazard_risk_map()
    create_settings_geom()
    create_settings_grid()
    create_vulnerability()
    create_vulnerability_win()
    gc.collect()
