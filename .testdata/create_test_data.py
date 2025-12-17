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

directories = (
    "exposure",
    "vulnerability",
)
fields = {
    "object_id": {"type": ogr.OFTInteger},
    "object_name": {"type": ogr.OFTString},
    "ref": {"type": ogr.OFTReal},
    "fn_damage_structure": {"type": ogr.OFTString},
    "max_damage_structure": {"type": ogr.OFTReal},
}
osr.UseExceptions()


def create_dbase_stucture():
    """Create directory structure, very difficult, yes.."""
    for d in directories:
        if not Path(p, d).exists():
            os.mkdir(Path(p, d))


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
    # In all honesty, this seems stupid
    if epsg is not None:
        driver = "GeoJSON"
        suffix = ".geojson"
        add = ""
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(epsg)

    # Set up the datasource
    dr = ogr.GetDriverByName(driver)
    src = dr.CreateDataSource(str(Path(p, "exposure", f"spatial{add}{suffix}")))
    layer = src.CreateLayer(
        f"spatial{add}",
        srs=srs,
        geom_type=3,
    )

    # Create the fields
    for key, item in fields.items():
        field = ogr.FieldDefn(
            key,
            item["type"],
        )
        if item["type"] == ogr.OFTString:
            field.SetWidth(20)
        layer.CreateField(field)

    # Set the geometries and the field values
    for idx, geom in enumerate(geoms):
        # Create the geometry and the feature
        geom = ogr.CreateGeometryFromWkt(geom)
        ft = ogr.Feature(layer.GetLayerDefn())
        # Alternate damage curve
        if (idx + 1) % 2 != 0:
            dmc = "struct_1"
        else:
            dmc = "struct_2"
        # Set the field values and geometry
        ft.SetField(0, idx + 1)
        ft.SetField(1, f"fp_{idx+1}")
        ft.SetField(2, 0)
        ft.SetField(3, dmc)
        ft.SetField(4, (idx + 1) * 1000)
        ft.SetGeometry(geom)
        # Add the feature to the layer
        layer.CreateFeature(ft)

    # Dereference everything
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

    # Set up the data source
    dr = ogr.GetDriverByName("GeoJSON")
    src = dr.CreateDataSource(str(Path(p, "exposure", "spatial2.geojson")))
    layer = src.CreateLayer(
        "spatial2",
        srs,
        3,
    )

    # Create the fields
    for key, item in fields.items():
        field = ogr.FieldDefn(
            key,
            item["type"],
        )
        if item["type"] == ogr.OFTString:
            field.SetWidth(20)
        layer.CreateField(field)

    # Create the geometry and feature
    geom = ogr.CreateGeometryFromWkt(geoms[0])
    ft = ogr.Feature(layer.GetLayerDefn())
    # Set the fields and geometry
    ft.SetField(0, 5)
    ft.SetField(1, f"fp_{5}")
    ft.SetField(2, 0)
    ft.SetField(3, "struct_1")
    ft.SetField(4, (5 + 1) * 1000)
    ft.SetGeometry(geom)
    # Add the feature to the layer
    layer.CreateFeature(ft)

    # Dereference everything
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

    # Set up the data source
    dr = ogr.GetDriverByName("GeoJSON")
    src = dr.CreateDataSource(str(Path(p, "exposure", "spatial_outside.geojson")))
    layer = src.CreateLayer(
        "spatial",
        srs,
        3,
    )

    # Create the fields
    for key, item in fields.items():
        field = ogr.FieldDefn(
            key,
            item["type"],
        )
        if item["type"] == ogr.OFTString:
            field.SetWidth(20)
        layer.CreateField(field)

    for idx, geom in enumerate(geoms):
        # Create the geometry and the feature
        geom = ogr.CreateGeometryFromWkt(geom)
        ft = ogr.Feature(layer.GetLayerDefn())
        # Alternate damage curve
        if (idx + 1) % 2 != 0:
            dmc = "struct_1"
        else:
            dmc = "struct_2"
        # Set the field values and geometry
        ft.SetField(0, idx + 1)
        ft.SetField(1, f"fp_{idx+1}")
        ft.SetField(2, 0)
        ft.SetField(3, dmc)
        ft.SetField(4, (idx + 1) * 1000)
        ft.SetGeometry(geom)
        # Add the feature to the layer
        layer.CreateFeature(ft)

    # Dereference everything
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

    # Set up the data source
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

    # Create the band
    band = src.GetRasterBand(1)
    data = zeros((10, 10))
    oneD = tuple(range(10))
    # Create spatially different data
    for x, y in product(oneD, oneD):
        data[x, y] = 2000 + ((x + y) * 100)
    # Write the data
    band.WriteArray(data)
    band.SetMetadataItem("fn_damage", "struct_1")

    # Flush the data
    band.FlushCache()
    src.FlushCache()

    # Dereference everything
    srs = None
    band = None
    src = None
    dr = None


def create_hazard_event_map(epsg: int = None):
    """Create hazard event map."""
    add = "_no_srs"
    if epsg is not None:
        add = ""

    # Set up the data source
    dr = gdal.GetDriverByName("netCDF")
    src = dr.Create(
        str(Path(p, f"event_map{add}.nc")),
        10,
        10,
        1,
        gdal.GDT_Float32,
    )
    # This is stupid
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

    # Create a band
    band = src.GetRasterBand(1)
    data = zeros((10, 10))
    oneD = tuple(range(10))
    # Create spatially different data
    for x, y in product(oneD, oneD):
        data[x, y] = 3.6 - ((x + y) * 0.2)
    # Write blyat
    band.WriteArray(data)

    # Flush the data
    band.FlushCache()
    src.FlushCache()

    # Dereference everything
    srs = None
    band = None
    src = None
    dr = None


def create_hazard_event_map_highres():
    """Create a high resolution hazard map to be reprojected."""
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)

    # Set up the data source
    dr = gdal.GetDriverByName("netCDF")
    src = dr.Create(
        str(Path(p, "event_map_highres.nc")),
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

    # Create band
    band = src.GetRasterBand(1)
    data = zeros((100, 100))
    oneD = tuple(range(100))
    # Create spatially different data
    for x, y in product(oneD, oneD):
        data[x, y] = 3.6 - ((x + y) * 0.02)
    # Write the data
    band.WriteArray(data)

    # Flush the data
    band.FlushCache()
    src.FlushCache()

    # Dereference everything
    srs = None
    band = None
    src = None
    dr = None


def create_hazard_risk_map():
    """Create a hazard map for risk calculations."""
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)

    # Set up the data source
    dr = gdal.GetDriverByName("netCDF")
    src = dr.Create(
        str(Path(p, "risk_map.nc")),
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
        # Create spatially different data
        for x, y in product(oneD, oneD):
            data[x, y] = 3.6 - ((x + y) * 0.2)
        data *= fc
        band.WriteArray(data)
        band.SetMetadataItem("rp", f"{rps[idx]}")
        band.FlushCache()
        band = None

    # Flush the source
    src.FlushCache()

    # Dereference
    srs = None
    src = None
    dr = None


def create_settings_geom():
    """Create exposure geometry model settings."""
    doc = {
        "model": {
            "type": "geom",
            "risk": False,
            "srs": {
                "value": "EPSG:4326",
            },
        },
        "output": {
            "path": "output/geom_event",
            "geom": [{"name": "spatial.gpkg"}],
        },
        "vulnerability": {
            "file": "vulnerability/curves.csv",
            "step_size": 0.01,
        },
        "hazard": {
            "file": "event_map.nc",
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

    # Setup toml with geometries lying outside hazard are
    doc_o = copy.deepcopy(doc)
    doc_o["exposure"]["geom"][0]["file"] = "exposure/spatial_outside.geojson"

    with open(Path(p, "geom_event_outside.toml"), "w") as f:
        tomlkit.dump(doc_o, f)

    # Setup toml for risk calculation
    doc_r = copy.deepcopy(doc)
    doc_r["model"]["risk"] = True
    doc_r["output"]["path"] = "output/geom_risk"
    doc_r["hazard"]["file"] = "risk_map.nc"
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
            "type": "grid",
            "risk": False,
            "srs": {
                "value": "EPSG:4326",
            },
        },
        "output": {
            "path": "output/grid_event",
            "grid": {"name": "output.nc"},
        },
        "vulnerability": {
            "file": "vulnerability/curves.csv",
            "step_size": 0.01,
        },
        "hazard": {
            "file": "event_map.nc",
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
    }

    # Dump directly
    with open(Path(p, "grid_event.toml"), "w") as f:
        tomlkit.dump(doc, f)

    # Set up for risk calculations
    doc_r = copy.deepcopy(doc)
    doc_r["model"]["risk"] = True
    doc_r["output"]["path"] = "output/grid_risk"
    doc_r["hazard"]["file"] = "risk_map.nc"
    doc_r["hazard"]["return_periods"] = [2, 5, 10, 25]
    doc_r["hazard"]["settings"].update({"var_as_band": True})

    with open(Path(p, "grid_risk.toml"), "w") as f:
        tomlkit.dump(doc_r, f)

    # With high resolution data
    doc_u = copy.deepcopy(doc)
    doc_u["hazard"]["file"] = "event_map_highres.nc"

    with open(Path(p, "grid_unequal.toml"), "w") as f:
        tomlkit.dump(doc_u, f)


def create_vulnerability():
    """Create vulnerability curves."""

    # Function for creating the curves
    def log_base(b, x):
        r = math.log(x) / math.log(b)
        if r < 0:
            return 0
        return r

    wd = arange(0, 5.25, 0.25)
    dc1 = [0.0] + [float(round(min(log_base(5, x), 0.96), 2)) for x in wd[1:]]
    dc2 = [0.0] + [float(round(min(log_base(3, x), 0.96), 2)) for x in wd[1:]]

    # Write to a csv
    with open(Path(p, "vulnerability", "curves.csv"), mode="wb") as f:
        f.write(b"#UNIT=meter\n")
        f.write(b"#method=mean,max\n")
        f.write(b"water depth,struct_1,struct_2\n")
        for idx, item in enumerate(wd):
            f.write(f"{item},{dc1[idx]},{dc2[idx]}\n".encode())


def create_vulnerability_win():
    """Create vulnerability curves with Windows newline char."""

    # Function for creating the curves
    def log_base(b, x):
        r = math.log(x) / math.log(b)
        if r < 0:
            return 0
        return r

    wd = arange(0, 5.25, 0.25)
    dc1 = [0.0] + [float(round(min(log_base(5, x), 0.96), 2)) for x in wd[1:]]
    dc2 = [0.0] + [float(round(min(log_base(3, x), 0.96), 2)) for x in wd[1:]]

    # Write to a csv
    with open(Path(p, "vulnerability", "curves_win.csv"), mode="wb") as f:
        f.write(b"#UNIT=meter\r\n")
        f.write(b"#method=mean,max\r\n")
        f.write(b"water depth,struct_1,struct_2\r\n")
        for idx, item in enumerate(wd):
            f.write(f"{item},{dc1[idx]},{dc2[idx]}\r\n".encode())


if __name__ == "__main__":
    create_dbase_stucture()
    create_exposure_geoms(epsg=4326)
    create_exposure_geoms(epsg=None)
    create_exposure_geoms_5th()
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
