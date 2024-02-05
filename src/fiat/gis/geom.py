"""Only vector methods for FIAT."""

import gc
from pathlib import Path

from osgeo import ogr, osr

from fiat.io import GeomSource, open_geom


def coor_transform():
    """_summary_."""
    pass


def geom_centroid(ft: ogr.Feature) -> tuple:
    """_summary_."""
    pass


def point_in_geom(
    ft: ogr.Feature,
) -> tuple:
    """Create a point within a polygon.

    This is in essence a very lazy centroid. Keep in mind though, it can differ quite
    a bit from the actual centroid.

    Parameters
    ----------
    ft : ogr.Feature
        The feature (polygon or linestring) in which to create the point.

    Returns
    -------
    tuple
        The x and y coordinate of the created point.
    """
    geom = ft.GetGeometryRef()
    p = geom.PointOnSurface()
    geom = None
    return p.GetX(), p.GetY()


def reproject_feature(
    ft: ogr.Feature,
    crs: str,
):
    """_summary_."""
    pass


def reproject(
    gs: GeomSource,
    crs: str,
    out_dir: Path | str = None,
):
    """Reproject a geometry layer.

    Parameters
    ----------
    gs : GeomSource
        Input object.
    crs : str
        Coodinates reference system (projection). An accepted format is: `EPSG:3857`.
    out_dir : Path | str, optional
        Output directory. If not defined, if will be inferred from the input object.

    Returns
    -------
    GeomSource
        Output object. A lazy reading of the just creating geometry file.
    """
    if not Path(str(out_dir)).is_dir():
        out_dir = gs.path.parent

    fname = Path(out_dir, f"{gs.path.stem}_repr_fiat{gs.path.suffix}")

    out_srs = osr.SpatialReference()
    out_srs.SetFromUserInput(crs)
    out_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

    transform = osr.CoordinateTransformation(
        gs.get_srs(),
        out_srs,
    )

    mem_gs = open_geom(
        file="memset",
        mode="w",
    )

    mem_gs.create_layer(
        out_srs,
        gs.layer.GetGeomType(),
    )
    mem_gs.set_layer_from_defn(
        gs.layer.GetLayerDefn(),
    )

    for ft in gs.layer:
        geom = ft.GetGeometryRef()
        geom.Transform(transform)

        ft.SetGeometry(geom)
        mem_gs.layer.CreateFeature(ft)

    geom = None
    ft = None
    out_srs = None
    transform = None

    with open_geom(fname, mode="w") as new_gs:
        new_gs.create_layer_from_copy(mem_gs.layer)

    mem_gs.close()
    del mem_gs
    gc.collect()

    return new_gs.reopen()
