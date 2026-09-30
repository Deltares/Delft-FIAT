"""Only vector methods for FIAT."""

import gc
from pathlib import Path

import numpy as np
from pyproj import CRS, Transformer

from fiat.driver.fgb import FlatGeobufWriter, Geometry
from fiat.gis import _geom


def point_in_geom(
    geometry: Geometry,
) -> tuple:
    """Create a representative interior point within a geometry.

    A GDAL-free replacement for ``OGRGeometry::PointOnSurface``. Keep in mind it can
    differ a bit from the true centroid for concave shapes.

    Parameters
    ----------
    geometry : Geometry
        The geometry (polygon) in which to create the point.

    Returns
    -------
    tuple
        The x and y coordinate of the created point.
    """
    return _geom.point_on_surface(geometry)


def _transform_xy(
    xy: np.ndarray,
    transformer: Transformer,
) -> np.ndarray:
    """Transform a flat interleaved x, y array to another CRS."""
    coords = np.asarray(xy, dtype=np.float64).reshape(-1, 2)
    if coords.shape[0] == 0:
        return coords.ravel()
    xt, yt = transformer.transform(coords[:, 0], coords[:, 1])
    out = np.empty(coords.shape, dtype=np.float64)
    out[:, 0] = xt
    out[:, 1] = yt
    return out.ravel()


def reproject_feature(
    geometry: Geometry,
    transformer: Transformer,
) -> tuple:
    """Transform the coordinates of a geometry.

    Parameters
    ----------
    geometry : Geometry
        The geometry.
    transformer : Transformer
        A pyproj coordinate transformer.

    Returns
    -------
    tuple
        The transformed ``(xy, ends, parts)`` arrays.
    """
    xy = _transform_xy(geometry.xy, transformer)
    return xy, geometry.ends, geometry.parts


def reproject(
    ds,
    dst_crs: str,
    chunk: int = 200000,
    output_dir: Path | str = None,
):
    """Reproject a geometry layer.

    Parameters
    ----------
    ds : FlatGeobufDriver
        Input object.
    dst_crs : str
        Spatial reference system (projection). An accepted format is: `EPSG:3857`.
    chunk : int, optional
        Unused (kept for API compatibility).
    output_dir : Path | str, optional
        Output directory. If not defined, it is inferred from the input object.

    Returns
    -------
    FlatGeobufDriver
        Output object. A lazy reading of the just created geometry file.
    """
    from fiat.open import open_geom

    output_dir = output_dir or ds.path.parent
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    fname = Path(output_dir, f"{ds.path.stem}_repr.fgb")

    layer = ds.layer
    src_crs = layer.crs
    dst = CRS.from_user_input(dst_crs)
    transformer = Transformer.from_crs(src_crs, dst, always_xy=True)

    # Destination CRS metadata.
    dst_wkt = dst.to_wkt()
    auth = dst.to_authority()
    dst_org, dst_code = ("", 0)
    if auth is not None:
        dst_org, dst_code = auth[0], int(auth[1])

    writer = FlatGeobufWriter(
        fname.as_posix(),
        col_names=list(layer.fields),
        col_types=list(layer.dtypes),
        geom_type=layer.geom_type,
        name=fname.stem,
        crs_wkt=dst_wkt,
        crs_org=dst_org,
        crs_code=dst_code,
    )

    for ft in layer:
        geom = ft.geometry
        xy = _transform_xy(geom.xy, transformer)
        writer.add_feature(xy, geom.ends, geom.parts, ft.values)

    writer.finalize()

    ds.close()
    gc.collect()

    return open_geom(fname.as_posix())
