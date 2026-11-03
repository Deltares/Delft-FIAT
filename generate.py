"""Create data to test with."""

import copy
import gc
import math
import os
import warnings
from itertools import product
from pathlib import Path

import numpy as np
import tomlkit

from generate_helpers import (
    fgb_writer,
    netcdf_dimension,
    netcdf_handle,
    netcdf_spatial_dimensions,
    netcdf_spatial_variable,
    netcdf_variable,
)

p = Path(Path(__file__).parent, "data")
p.mkdir(exist_ok=True)

directories = ("exposure",)

# Suppress some warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)


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
    add = "" if epsg is not None else "_no_crs"
    fgb_writer(
        Path(p, "exposure", f"spatial{add}.fgb"),
        f"spatial{add}",
        geoms,
        epsg=epsg,
    )


def create_exposure_geoms_5th():
    """Create vector file with fifth geometry for calculation."""
    geoms = ("POLYGON ((2.5 7.5, 3.5 7.5, 3.5 6.5, 2.5 6.5, 2.5 7.5))",)
    fgb_writer(
        Path(p, "exposure", "spatial2.fgb"),
        "spatial2",
        geoms,
        epsg=4326,
    )


def create_exposure_geoms_outside():
    """Create vector data that lies outside of hazard."""
    geoms = (
        "POLYGON ((0.5 11.5, 0.5 10.5, 1.5 10.5, 1.5 11.5, 0.5 11.5))",
        "POLYGON ((4.5 10.5, 4.5 9.5, 5.5 9.5, 5.5 10.5, 4.5 10.5))",
        "POLYGON ((8.5 9.5, 8.5 8.5, 9.5 8.5, 9.5 9.5, 8.5 9.5))",
    )
    fgb_writer(
        Path(p, "exposure", "spatial_outside.fgb"),
        "spatial",
        geoms,
        epsg=4326,
    )


def create_exposure_geoms_types():
    """Create basic vector file with 4 geometries and 2 impact types."""
    geoms = (
        "POLYGON ((0.5 9.5, 0.5 8.5, 1.5 8.5, 1.5 9.5, 0.5 9.5))",
        "POLYGON ((4.5 5.5, 4.5 2.5, 6.5 2.5, 6.5 3.5, 5.5 3.5, 5.5 5.5, 4.5 5.5))",
        "POLYGON ((1.5 1.05, 2.5 3.95, 3.5 1.05, 1.5 1.05))",
        "POLYGON ((6.05 7.95, 8.95 7.95, 8.5 6.05, 6.5 6.05, 6.05 7.95))",
    )
    fgb_writer(
        Path(p, "exposure", "spatial_types.fgb"),
        "spatial_types",
        geoms,
        epsg=4326,
        types=("damage", "affected"),
    )


def create_exposure_grid():
    """Create raster file with exposure data for grid model."""
    ds = netcdf_handle(fname=Path(p, "exposure", "spatial.nc"))
    netcdf_spatial_dimensions(
        ds=ds,
        lats=np.arange(9.5, 0.4, -1),
        lons=np.arange(0.5, 9.6, 1),
        crs="EPSG:4326",
    )

    # Setup variables 1
    var = netcdf_spatial_variable(ds=ds, name="exposure1")
    data = np.ones((10, 10)) * -9999
    # Create spatially different data
    data[0, 1] = 2200
    data[1, 5] = 3500
    data[5, 6] = 2700
    data[3, 9] = 5100
    data[9, 2] = 4600
    data[8, 8] = 3200
    # Write the data
    var.setncattr("fn_curve", "struct_1")
    var.setncattr("type", "default")
    var[:] = data
    # Flush the data
    ds.sync()
    var = None

    # Setup band 2
    var = netcdf_spatial_variable(ds=ds, name="exposure2")
    data = np.ones((10, 10)) * -9999
    # Create spatially different data
    data[0, 1] = 3100
    data[1, 6] = 4400
    data[5, 6] = 3600
    data[4, 4] = 7000
    data[3, 9] = 6000
    data[9, 2] = 5500
    data[8, 8] = 4100
    # Write the data
    var.setncattr("fn_curve", "struct_2")
    var.setncattr("type", "default")
    var[:] = data
    # Flush the data
    ds.sync()
    var = None

    # Flush the dataaset
    ds.close()

    # Dereference everything
    ds = None


def create_exposure_categorized_grid():
    """Create raster file with exposure data for grid model."""
    ds = netcdf_handle(fname=Path(p, "exposure", "spatial_cat.nc"))
    netcdf_spatial_dimensions(
        ds=ds,
        lats=np.arange(9.5, 0.4, -1),
        lons=np.arange(0.5, 9.6, 1),
        crs="EPSG:4326",
    )
    netcdf_dimension(
        ds=ds,
        name="exposure_cat",
        values=np.array([0, 1, 2]),
        dtype="i4",
    )

    # Setup spatial variable
    var = netcdf_spatial_variable(ds=ds, name="exposure", dtype="i4", fill_value=0)
    data = np.zeros((10, 10), dtype=np.int32)
    # Create spatially different data
    data[0, 1] = 1
    data[1, 5] = 2
    data[5, 6] = 2
    data[3, 9] = 1
    data[9, 2] = 2
    data[8, 8] = 1
    # Set the metadata
    var.setncattr("categories", [0, 1, 2])
    var.setncattr("type", "categorized")

    # Setup the category variable
    var2 = netcdf_variable(
        ds=ds,
        name="exposure_values",
        dims=("exposure_cat",),
        dtype="i4",
        fill_value=-9999,
    )

    # Setup a second category variable
    var3 = netcdf_variable(
        ds=ds,
        name="exposure_values2",
        dims=("exposure_cat",),
        dtype="i4",
        fill_value=-9999,
    )

    # Write the data
    var[:] = data
    var2[:] = np.array([0, 5000, 3000], dtype=np.int32)
    var3[:] = np.array([0, 2500, 1500], dtype=np.int32)

    # Flush the data
    ds.sync()
    var = None
    var2 = None
    var3 = None


def create_hazard_event_map(fname: Path | str, crs: str = None):
    """Create hazard event map."""
    ds = netcdf_handle(fname=Path(p, fname))
    netcdf_spatial_dimensions(
        ds=ds,
        lats=np.arange(9.5, 0.4, -1),
        lons=np.arange(0.5, 9.6, 1),
        crs=crs,
    )

    # Create the variables
    var = netcdf_spatial_variable(ds=ds, name="data")

    # Create the data
    data = np.zeros((10, 10))
    oneD = tuple(range(10))
    # Create spatially different data
    for x, y in product(oneD, oneD):
        data[x, y] = 3.6 - ((x + y) * 0.2)
    # Write blyat
    var.setncattr("type", "water_depth")
    var[:] = data

    # Flush the data
    ds.sync()
    ds.close()

    # Dereference everything
    var = None
    ds = None


def create_hazard_event_map_highres():
    """Create a high resolution hazard map to be reprojected."""
    ds = netcdf_handle(fname=Path(p, "event_map_highres.nc"))
    netcdf_spatial_dimensions(
        ds=ds,
        lats=np.arange(0.05, 9.96, 0.1),
        lons=np.arange(9.95, 0.04, -0.1),
        crs="EPSG:4326",
    )

    # Create the variable
    var = netcdf_spatial_variable(ds=ds, name="data")

    # Create the data
    data = np.zeros((100, 100))
    oneD = tuple(range(100))

    # Create spatially different data
    for x, y in product(oneD, oneD):
        data[x, y] = 3.6 - ((x + y) * 0.02)

    # Write the data
    var.setncattr("type", "water_depth")
    var[:] = data

    # Flush the data
    ds.sync()
    ds.close()

    # Dereference everything
    var = None
    ds = None


def create_hazard_risk_map():
    """Create a hazard map for risk calculations."""
    ds = netcdf_handle(fname=Path(p, "risk_map.nc"))
    netcdf_spatial_dimensions(
        ds=ds,
        lats=np.arange(9.5, 0.4, -1),
        lons=np.arange(0.5, 9.6, 1),
        crs="EPSG:4326",
    )

    # Set return periods values
    rps = [2, 5, 10, 25]
    for idx, fc in enumerate((1.5, 1.8, 1.9, 1.95)):
        var = netcdf_spatial_variable(ds=ds, name=f"{rps[idx]}Y")
        data = np.zeros((10, 10))
        oneD = tuple(range(10))
        # Create spatially different data
        for x, y in product(oneD, oneD):
            data[x, y] = 3.6 - ((x + y) * 0.2)
        data *= fc
        # Set the attributes
        var.setncattr("rp", f"{rps[idx]}")
        var.setncattr("type", "water_depth")
        # Set the data
        var[:] = data
        var = None

    # Flush the source
    ds.sync()
    ds.close()

    # Dereference
    ds = None


def write_depth_duration(ds, fc: float, duration: float, rp: int | None = None):
    """Write a flood depth and a flood duration band to a netcdf file."""
    # Create the data
    data = np.zeros((10, 10))
    oneD = tuple(range(10))
    # Create spatially different data
    for x, y in product(oneD, oneD):
        data[x, y] = 3.6 - ((x + y) * 0.2)
    data *= fc

    # Write the depth and duration (only where it is wet)
    suffix = "" if rp is None else f"_{rp}Y"
    for name, type, values in (
        ("depth", "water_depth", data),
        ("duration", "duration", np.where(data > 0, duration, 0.0)),
    ):
        var = netcdf_spatial_variable(ds=ds, name=f"{name}{suffix}")
        if rp is not None:
            var.setncattr("rp", f"{rp}")
        var.setncattr("type", type)
        var[:] = values
        var = None


def create_hazard_duration_maps():
    """Create hazard maps with both flood depth and flood duration bands."""
    # Event map
    ds = netcdf_handle(fname=Path(p, "event_map_duration.nc"))
    netcdf_spatial_dimensions(
        ds=ds,
        lats=np.arange(9.5, 0.4, -1),
        lons=np.arange(0.5, 9.6, 1),
        crs="EPSG:4326",
    )
    write_depth_duration(ds, fc=1.0, duration=3.0)
    ds.sync()
    ds.close()

    # Risk map
    ds = netcdf_handle(fname=Path(p, "risk_map_duration.nc"))
    netcdf_spatial_dimensions(
        ds=ds,
        lats=np.arange(9.5, 0.4, -1),
        lons=np.arange(0.5, 9.6, 1),
        crs="EPSG:4326",
    )
    for rp, fc, duration in zip(
        (2, 5, 10, 25),
        (1.5, 1.8, 1.9, 1.95),
        (1.0, 2.0, 3.0, 5.0),
    ):
        write_depth_duration(ds, fc=fc, duration=duration, rp=rp)
    ds.sync()
    ds.close()

    # Dereference
    ds = None


def create_settings_geom():
    """Create exposure geometry model settings."""
    doc = {
        "type": "geom",
        "risk": False,
        "output_dir": "output/geom_event",
        "projection": {
            "crs": "EPSG:4326",
        },
        "output": [{"file": "spatial.fgb"}],
        "vulnerability": {
            "file": "curves.nc",
        },
        "hazard": {
            "file": "event_map.nc",
            "settings": {
                "crs": "EPSG:4326",
            },
        },
        "exposure": [
            {
                "file": "exposure/spatial.fgb",
                "area_method": "area",
                "settings": {
                    "crs": "EPSG:4326",
                },
            },
        ],
    }

    # Dump directly as default event toml
    with open(Path(p, "geom_event.toml"), "w") as f:
        tomlkit.dump(doc, f)

    # Setup toml with two geometry files
    doc2g = copy.deepcopy(doc)
    doc2g["output_dir"] = "output/geom_event_2g"
    doc2g["output"].append({"file": "spatial2.fgb"})
    doc2g["exposure"].append({"file": "exposure/spatial2.fgb"})

    with open(Path(p, "geom_event_2g.toml"), "w") as f:
        tomlkit.dump(doc2g, f)

    # Setup toml with geometries lying outside hazard are
    doc_o = copy.deepcopy(doc)
    doc_o["exposure"][0]["file"] = "exposure/spatial_outside.fgb"

    with open(Path(p, "geom_event_outside.toml"), "w") as f:
        tomlkit.dump(doc_o, f)

    # Setup toml for risk calculation
    doc_r = copy.deepcopy(doc)
    doc_r["risk"] = True
    doc_r["output_dir"] = "output/geom_risk"
    doc_r["hazard"]["file"] = "risk_map.nc"
    doc_r["hazard"]["return_periods"] = [2, 5, 10, 25]

    with open(Path(p, "geom_risk.toml"), "w") as f:
        tomlkit.dump(doc_r, f)

    # Setup toml for risk calculation with 2 geometries
    doc_r2g = copy.deepcopy(doc_r)
    doc_r2g["output_dir"] = "output/geom_risk_2g"
    doc_r2g["output"].append({"file": "spatial2.fgb"})
    doc_r2g["exposure"].append({"file": "exposure/spatial2.fgb"})

    with open(Path(p, "geom_risk_2g.toml"), "w") as f:
        tomlkit.dump(doc_r2g, f)


def create_settings_grid():
    """Create exposure grid model settings."""
    doc = {
        "type": "grid",
        "risk": False,
        "output_dir": "output/grid_event",
        "projection": {
            "crs": "EPSG:4326",
        },
        "output": {"file": "output.tif"},
        "vulnerability": {
            "file": "curves.nc",
        },
        "hazard": {
            "file": "event_map.nc",
            "settings": {
                "crs": "EPSG:4326",
            },
        },
        "exposure": {
            "file": "exposure/spatial.nc",
            "settings": {
                "crs": "EPSG:4326",
            },
        },
    }

    # Dump directly
    with open(Path(p, "grid_event.toml"), "w") as f:
        tomlkit.dump(doc, f)

    # Set up for risk calculations
    doc_r = copy.deepcopy(doc)
    doc_r["risk"] = True
    doc_r["output_dir"] = "output/grid_risk"
    doc_r["hazard"]["file"] = "risk_map.nc"
    doc_r["hazard"]["return_periods"] = [2, 5, 10, 25]

    with open(Path(p, "grid_risk.toml"), "w") as f:
        tomlkit.dump(doc_r, f)

    # With high resolution data
    doc_u = copy.deepcopy(doc)
    doc_u["output_dir"] = "output/grid_ueq"
    doc_u["hazard"]["file"] = "event_map_highres.nc"

    with open(Path(p, "grid_unequal.toml"), "w") as f:
        tomlkit.dump(doc_u, f)

    # With catagorized exposure data
    doc_c = copy.deepcopy(doc)
    doc_c["output_dir"] = "output/grid_cat"
    doc_c["exposure"]["file"] = "exposure/spatial_cat.nc"
    doc_c["vulnerability"]["file"] = "curves_cat.nc"

    with open(Path(p, "grid_cat.toml"), "w") as f:
        tomlkit.dump(doc_c, f)


def create_settings_multi():
    """Create settings for the multi-vulnerability (dataset) models."""

    def dump(doc: dict, name: str):
        doc["output_dir"] = f"output/{name}"
        with open(Path(p, f"{name}.toml"), "w") as f:
            tomlkit.dump(doc, f)

    base = {
        "type": "grid",
        "risk": False,
        "projection": {
            "crs": "EPSG:4326",
        },
        "output": {"file": "output.tif"},
        "vulnerability": {
            "file": "curves_multi.nc",
        },
        "hazard": {
            "file": "event_map_duration.nc",
            "settings": {
                "crs": "EPSG:4326",
            },
        },
        "exposure": {
            "file": "exposure/spatial.nc",
            "vulnerability": "default",
            "settings": {
                "crs": "EPSG:4326",
            },
        },
    }

    # Grid, multiple datasets combined in one method call
    doc = copy.deepcopy(base)
    doc["exposure"]["variables"] = [
        {"name": "exposure2", "vulnerability": ["direct", "indirect"]},
    ]
    dump(doc, "grid_multi_combined")

    # Grid, multiple datasets each their own method call
    doc = copy.deepcopy(base)
    doc["exposure"]["variables"] = [
        {"name": "exposure2", "vulnerability": ["default", "default_2d"]},
    ]
    dump(doc, "grid_multi_separate")

    # Grid, one 2D dataset
    doc = copy.deepcopy(base)
    doc["exposure"]["vulnerability"] = "default_2d"
    dump(doc, "grid_2d")

    # Grid, missing (unknown) hazard variable
    doc_m = copy.deepcopy(doc)
    doc_m["hazard"]["variables"] = [{"name": "nope"}]
    dump(doc_m, "grid_missing_variable")

    # Grid, settings overriding the netcdf attributes
    doc_o = copy.deepcopy(doc)
    doc_o["vulnerability"]["variables"] = [
        {
            "name": "default_2d",
            "method": "flood.depth_duration_2d",
            "types": {
                "depth_default_2d": "water_depth",
                "duration_default_2d": "duration",
            },
        },
    ]
    doc_o["hazard"]["variables"] = [
        {"name": "depth", "type": "water_depth"},
        {"name": "duration", "type": "duration"},
    ]
    doc_o["exposure"]["variables"] = [
        {"name": "exposure1", "fn_curve": "struct_2"},
    ]
    dump(doc_o, "grid_override")

    # Grid, uniform hazard and exposure layers
    doc = copy.deepcopy(base)
    doc["hazard"]["file"] = "event_map.nc"
    doc["hazard"]["variables"] = [
        {"name": "duration", "type": "duration", "value": 3.0},
    ]
    doc["exposure"]["vulnerability"] = "default_2d"
    doc["exposure"]["variables"] = [
        {
            "name": "exposure3",
            "type": "default",
            "fn_curve": "struct_1",
            "value": 1500.0,
        },
    ]
    dump(doc, "grid_uniform")

    # Grid, uniform hazard layers per return period
    doc = copy.deepcopy(base)
    doc["risk"] = True
    doc["hazard"]["file"] = "risk_map.nc"
    doc["hazard"]["return_periods"] = [2, 5, 10, 25]
    doc["hazard"]["variables"] = [
        {"name": f"duration_{rp}Y", "type": "duration", "value": dur, "rp": rp}
        for rp, dur in zip((2, 5, 10, 25), (1.0, 2.0, 3.0, 5.0))
    ]
    doc["exposure"]["variables"] = [
        {"name": "exposure2", "vulnerability": ["direct", "indirect"]},
    ]
    dump(doc, "grid_uniform_risk")

    # Grid, categorized with variables
    doc_c = copy.deepcopy(base)
    doc_c["vulnerability"]["file"] = "curves_cat.nc"
    doc_c["exposure"]["file"] = "exposure/spatial_cat.nc"
    doc = copy.deepcopy(doc_c)
    doc["exposure"]["variables"] = [
        {
            "name": "exposure",
            "type": "categorized",
            "vulnerability": "default",
            "values": ["exposure_values", "exposure_values2"],
        },
        {"name": "exposure_values2", "vulnerability": "default_2d"},
    ]
    dump(doc, "grid_cat_variables")

    # Grid, categorized with a uniform categorized layer
    doc = copy.deepcopy(doc_c)
    doc["exposure"]["variables"] = [
        {
            "name": "exposure",
            "type": "categorized",
            "values": ["exposure_values2"],
        },
        {
            "name": "exposure_uniform",
            "type": "categorized",
            "value": 1,
            "values": ["exposure_values"],
        },
    ]
    dump(doc, "grid_cat_uniform")

    # Geometry, one 2D dataset
    doc_g = copy.deepcopy(base)
    doc_g["type"] = "geom"
    doc_g["output"] = [{"file": "spatial.fgb"}]
    doc_g["exposure"] = [
        {
            "file": "exposure/spatial.fgb",
            "area_method": "area",
            "vulnerability": "default_2d",
            "settings": {
                "crs": "EPSG:4326",
            },
        },
    ]
    dump(copy.deepcopy(doc_g), "geom_2d")

    # Geometry, risk with one 2D dataset and two impact types
    doc = copy.deepcopy(doc_g)
    doc["risk"] = True
    doc["hazard"]["file"] = "risk_map_duration.nc"
    doc["hazard"]["return_periods"] = [2, 5, 10, 25]
    doc["output"] = [{"file": "spatial_types.fgb"}]
    doc["exposure"][0]["file"] = "exposure/spatial_types.fgb"
    doc["exposure"][0]["impact_type"] = ["damage", "affected"]
    dump(doc, "geom_2d_risk")

    # Geometry, uniform hazard layer
    doc = copy.deepcopy(doc_g)
    doc["hazard"]["file"] = "event_map.nc"
    doc["hazard"]["variables"] = [
        {"name": "duration", "type": "duration", "value": 3.0},
    ]
    dump(doc, "geom_uniform")


def log_base(b: float, x: float) -> float:
    """Logarithm with base b, floored at zero (also for x == 0)."""
    if x <= 0:
        return 0.0
    r = math.log(x) / math.log(b)
    if r < 0:
        return 0.0
    return r


def curve_1d(b: float, wd: np.ndarray) -> list[float]:
    """Create a 1D (depth) vulnerability curve."""
    return [float(round(min(log_base(b, x), 0.96), 2)) for x in wd]


def curve_2d(b: float, wd: np.ndarray, dur: np.ndarray) -> np.ndarray:
    """Create a 2D (depth x duration) vulnerability curve."""
    data = np.zeros((len(wd), len(dur)), dtype=np.float32)
    for (i, d), (j, t) in product(enumerate(wd), enumerate(dur)):
        data[i, j] = min(log_base(b, d), 0.96) * min(1, 0.5 + t / 20)
    return data


def write_vulnerability_1d(
    ds,
    name: str,
    ids: np.ndarray,
    method: str,
    index: str = "depth",
    type: str = "water_depth",
    dtype: str = "str",
):
    """Write a 1D vulnerability dataset to a netcdf file."""
    wd = np.arange(0, 5.25, 0.25)
    netcdf_dimension(ds, name=f"{index}_{name}", values=wd)
    ds.variables[f"{index}_{name}"].setncattr("type", type)
    netcdf_dimension(ds, name=f"curve_{name}", values=ids, dtype=dtype)

    # Create the netcdf variable
    var = netcdf_variable(ds, name=name, dims=(f"{index}_{name}", f"curve_{name}"))
    var.setncattr("method", method)
    # Create array
    data = np.zeros((len(wd), 2), dtype=np.float32)

    # Define the data
    data[:, 0] = curve_1d(5, wd)
    data[:, 1] = curve_1d(3, wd)

    # Set the data
    var[:] = data
    var = None


def write_vulnerability_2d(
    ds,
    name: str,
    ids: np.ndarray,
    dtype: str = "str",
):
    """Write a 2D (depth x duration) vulnerability dataset to a netcdf file."""
    wd = np.arange(0, 5.25, 0.25)
    dur = np.array([0, 1, 2, 5, 10], dtype=np.float32)
    netcdf_dimension(ds, name=f"depth_{name}", values=wd)
    ds.variables[f"depth_{name}"].setncattr("type", "water_depth")
    netcdf_dimension(ds, name=f"duration_{name}", values=dur)
    ds.variables[f"duration_{name}"].setncattr("type", "duration")
    netcdf_dimension(ds, name=f"curve_{name}", values=ids, dtype=dtype)

    # Create the netcdf variable
    var = netcdf_variable(
        ds,
        name=name,
        dims=(f"depth_{name}", f"duration_{name}", f"curve_{name}"),
    )
    var.setncattr("method", "flood.depth_duration_2d")
    # Create array
    data = np.zeros((len(wd), len(dur), 2), dtype=np.float32)

    # Define the data
    data[:, :, 0] = curve_2d(5, wd, dur)
    data[:, :, 1] = curve_2d(3, wd, dur)

    # Set the data
    var[:] = data
    var = None


def create_table(fname: str = "table.csv", newline: str = "\n"):
    """Create a generic csv table (curves with metadata header rows)."""
    wd = np.arange(0, 5.25, 0.25)
    dc1 = curve_1d(5, wd)
    dc2 = curve_1d(3, wd)

    # Write to a csv
    with open(Path(p, fname), mode="wb") as f:
        f.write(f"#UNIT=meter{newline}".encode())
        f.write(f"#method=mean,max{newline}".encode())
        f.write(f"depth,struct_1,struct_2{newline}".encode())
        for idx, item in enumerate(wd):
            f.write(f"{item},{dc1[idx]},{dc2[idx]}{newline}".encode())


def create_vulnerability():
    """Create vulnerability curves."""
    ds = netcdf_handle(Path(p, "curves.nc"))
    write_vulnerability_1d(
        ds,
        name="default",
        ids=np.array(["struct_1", "struct_2"]),
        method="flood.depth",
    )

    # Sync and close
    ds.sync()
    ds.close()


def create_vulnerability_2d():
    """Create 2D (depth x duration) vulnerability curves."""
    ds = netcdf_handle(Path(p, "curves_2d.nc"))
    write_vulnerability_2d(ds, name="default", ids=np.array(["struct_1", "struct_2"]))

    # Sync and close
    ds.sync()
    ds.close()


def create_vulnerability_categorized():
    """Create vulnerability curves with integers as headers (categorized)."""
    ds = netcdf_handle(Path(p, "curves_cat.nc"))
    write_vulnerability_1d(
        ds,
        name="default",
        ids=np.array([1, 2]),
        method="flood.depth",
        dtype="i4",
    )
    write_vulnerability_2d(ds, name="default_2d", ids=np.array([1, 2]), dtype="i4")

    # Sync and close
    ds.sync()
    ds.close()


def create_vulnerability_multi():
    """Create a vulnerability file with multiple datasets."""
    ids = np.array(["struct_1", "struct_2"])
    ds = netcdf_handle(Path(p, "curves_multi.nc"))
    write_vulnerability_1d(ds, name="default", ids=ids, method="flood.depth")
    write_vulnerability_2d(ds, name="default_2d", ids=ids)
    write_vulnerability_1d(
        ds,
        name="direct",
        ids=ids,
        method="flood.depth_duration",
    )
    write_vulnerability_1d(
        ds,
        name="indirect",
        ids=ids,
        method="flood.depth_duration",
        index="days",
        type="duration",
    )

    # Sync and close
    ds.sync()
    ds.close()


if __name__ == "__main__":
    create_dbase_stucture()
    create_exposure_geoms(epsg=4326)
    create_exposure_geoms(epsg=None)
    create_exposure_geoms_5th()
    create_exposure_geoms_outside()
    create_exposure_geoms_types()
    create_exposure_grid()
    create_exposure_categorized_grid()
    create_hazard_event_map(fname="event_map.nc", crs="EPSG:4326")
    create_hazard_event_map(fname="event_map_no_crs.nc", crs=None)
    create_hazard_event_map_highres()
    create_hazard_risk_map()
    create_hazard_duration_maps()
    create_settings_geom()
    create_settings_grid()
    create_settings_multi()
    create_table()
    create_table(fname="table_win.csv", newline="\r\n")
    create_vulnerability()
    create_vulnerability_2d()
    create_vulnerability_categorized()
    create_vulnerability_multi()
    gc.collect()
