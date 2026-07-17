"""Only vector methods for FIAT."""

import gc
from pathlib import Path

from osgeo import ogr, osr

from fiat.fio import GeomIO
from fiat.model.geom_writer import GeomWriter
from fiat.open import open_geom


def point_in_geom(
    geometry: ogr.Geometry,
) -> tuple:
    """Create a point within a polygon.

    This is in essence a very lazy centroid. Keep in mind though, it can differ quite
    a bit from the actual centroid.

    Parameters
    ----------
    ft : ogr.Geometry
        The feature geometry (polygon or linestring) in which to create the point.

    Returns
    -------
    tuple
        The x and y coordinate of the created point.
    """
    p = geometry.PointOnSurface()
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
    src = osr.SpatialReference()
    src.SetFromUserInput(src_crs)
    src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    dst = osr.SpatialReference()
    dst.SetFromUserInput(dst_crs)
    dst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

    transform = osr.CoordinateTransformation(src, dst)
    geometry.Transform(transform)

    src = None
    dst = None
    transform = None

    return geometry


def reproject(
    ds: GeomIO,
    dst_crs: str,
    chunk: int = 200000,
    output_dir: Path | str = None,
):
    """Reproject a geometry layer.

    Parameters
    ----------
    ds : GeomIO
        Input object.
    dst_crs : str
        Spatial reference system (projection). An accepted format is: `EPSG:3857`.
    chunk : int, optional
        The size of the chunks used during reprojecting.
    output_dir : Path | str, optional
        Output directory. If not defined, if will be inferred from the input object.

    Returns
    -------
    GeomIO
        Output object. A lazy reading of the just creating geometry file.
    """
    output_dir = output_dir or ds.path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    fname = Path(output_dir, f"{ds.path.stem}_repr.fgb")

    src_crs = osr.SpatialReference()
    src_crs.SetFromUserInput(ds.layer.crs.to_wkt())
    src_crs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    out_crs = osr.SpatialReference()
    out_crs.SetFromUserInput(dst_crs)
    out_crs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    layer_defn = ds.layer.defn

    transform = osr.CoordinateTransformation(
        src_crs,
        out_crs,
    )

    with open_geom(fname, mode="w", overwrite=True) as new_gs:
        new_gs.create_layer(out_crs.ExportToWkt(), ds.layer.geom_type)
        new_gs.layer.set_from_defn(layer_defn)

    mem_gs = GeomWriter(
        fname,
        buffer_size=chunk,
    )
    mem_gs.setup(
        defn=layer_defn,
        crs=out_crs.ExportToWkt(),
    )

    for ft in ds.layer:
        geom = ft.GetGeometryRef()
        geom.Transform(transform)

        new_ft = ogr.Feature(mem_gs.buffer.layer.defn)
        new_ft.SetFrom(ft)
        new_ft.SetGeometry(geom)
        mem_gs.add_feature(new_ft)

    geom = None
    ft = None
    new_ft = None
    out_crs = None
    transform = None
    layer_defn = None

    mem_gs.close()
    mem_gs = None
    ds.close()
    ds = None
    gc.collect()

    return open_geom(fname)
