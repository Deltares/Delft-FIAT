from delft_fiat.io import open_geom

import gc
from osgeo import ogr
from osgeo import osr
from pathlib import Path


def coor_transform():
    raise NotImplementedError("coor_transform is not implemented yet")


def geom_centroid(ft: ogr.Feature) -> tuple:
    raise NotImplementedError("geom_centroid is not implemented yet")


def point_in_geom(
    ft: ogr.Feature,
) -> tuple:
    """Get X and Y coordinates of the point on the surface of the geometry

    Parameters
    ----------
    ft : ogr.Feature
        Vector feature

    Returns
    -------
    tuple
        X and Y coordinates of the point on the surface of the geometry
    """

    # Get the geometry reference system
    geom = ft.GetGeometryRef()

    # Get the point on the surface of the geometry
    p = geom.PointOnSurface()
    geom = None

    # Return the coordinates of the point
    return p.GetX(), p.GetY()


def reproject_feature(
    ft: ogr.Feature,
    crs: str,
):
    raise NotImplementedError("reproject_feature is not implemented yet")


def reproject(
    gs: "GeomSource",
    crs: str,
    out: str = None,
):
    """
    Reproject a GeomSource to a new coordinate reference system

    Parameters
    ----------
    gs : GeomSource
        Geometry source file
    crs : str
        New coordinate reference system
    out : str
        Output file path

    Returns
    -------
    GeomSource
        Reprojected geometry source file
    """

    # Get the output file path
    if not Path(str(out)).is_dir():
        out = gs.path.parent

    # Create the output file name
    fname = Path(out, f"{gs.path.stem}_repr_fiat{gs.path.suffix}")

    # Create the output file
    out_srs = osr.SpatialReference()
    out_srs.SetFromUserInput(crs)
    out_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

    # Create the coordinate transformation
    transform = osr.CoordinateTransformation(
        gs.get_srs(),
        out_srs,
    )

    # Create the output file
    mem_gs = open_geom(
        file="memset",
        mode="w",
    )

    # Create the output layer
    mem_gs.create_layer(
        out_srs,
        gs.layer.GetGeomType(),
    )
    mem_gs.set_layer_from_defn(
        gs.layer.GetLayerDefn(),
    )

    # Reproject the features
    for ft in gs.layer:
        geom = ft.GetGeometryRef()
        geom.Transform(transform)

        ft.SetGeometry(geom)
        mem_gs.layer.CreateFeature(ft)

    geom = None
    ft = None
    out_srs = None
    transform = None

    # Create the output file
    with open_geom(fname, mode="w") as new_gs:
        new_gs.create_layer_from_copy(mem_gs.layer)

    # Close the memory file
    mem_gs.close()
    del mem_gs
    gc.collect()

    # Reopen the new output file
    return new_gs.reopen()
