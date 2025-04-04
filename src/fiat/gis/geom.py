"""Only vector methods for FIAT."""

import gc
from pathlib import Path

from osgeo import ogr, osr

from fiat.fio import BufferedGeomWriter, GeomSource, open_geom


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
    geometry: ogr.Geometry,
    src_crs: str,
    dst_crs: str,
) -> ogr.Feature:
    """Transform geometry/ geometries of a feature.

    Parameters
    ----------
    geometry : ogr.Geometry
        The geometry.
    src_crs : str
        Coordinate reference system of the feature.
    dst_crs : str
        Coordinate reference system to which the feature is transformed.
    """
    src_srs = osr.SpatialReference()
    src_srs.SetFromUserInput(src_crs)
    src_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    dst_srs = osr.SpatialReference()
    dst_srs.SetFromUserInput(dst_crs)
    src_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

    transform = osr.CoordinateTransformation(src_srs, dst_srs)
    geometry.Transform(transform)

    src_srs = None
    dst_srs = None
    transform = None


def reproject(
    gs: GeomSource,
    crs: str,
    chunk: int = 200000,
    out_dir: Path | str = None,
):
    """Reproject a geometry layer.

    Parameters
    ----------
    gs : GeomSource
        Input object.
    crs : str
        Coodinates reference system (projection). An accepted format is: `EPSG:3857`.
    chunk : int, optional
        The size of the chunks used during reprojecting.
    out_dir : Path | str, optional
        Output directory. If not defined, if will be inferred from the input object.

    Returns
    -------
    GeomSource
        Output object. A lazy reading of the just creating geometry file.
    """
    if not Path(str(out_dir)).is_dir():
        out_dir = gs.path.parent

    fname = Path(out_dir, f"{gs.path.stem}_repr{gs.path.suffix}")

    out_srs = osr.SpatialReference()
    out_srs.SetFromUserInput(crs)
    out_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    layer_defn = gs.layer.GetLayerDefn()

    transform = osr.CoordinateTransformation(
        gs.srs,
        out_srs,
    )

    with open_geom(fname, mode="w", overwrite=True) as new_gs:
        new_gs.create_layer(out_srs, layer_defn.GetGeomType())
        new_gs.set_layer_from_defn(layer_defn)

    mem_gs = BufferedGeomWriter(
        fname,
        srs=out_srs,
        layer_defn=gs.layer.GetLayerDefn(),
        buffer_size=chunk,
    )

    for ft in gs.layer:
        geom = ft.GetGeometryRef()
        geom.Transform(transform)

        new_ft = ogr.Feature(mem_gs.buffer.layer.GetLayerDefn())
        new_ft.SetFrom(ft)
        new_ft.SetGeometry(geom)
        mem_gs.add_feature(new_ft)

    geom = None
    ft = None
    new_ft = None
    out_srs = None
    transform = None
    layer_defn = None

    mem_gs.close()
    mem_gs = None
    gs.close()
    gs = None
    gc.collect()

    return open_geom(fname)
