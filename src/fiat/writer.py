"""Output grid writer helpers."""

from pathlib import Path

import numpy as np

from fiat.driver.geotiff import GeotiffWriter

__all__ = ["create_geotiff_handle"]


def create_geotiff_handle(
    path: Path | str,
    variables: list[str],
    ds_like,
    crs=None,
    tile: tuple[int, int] | None = None,
) -> GeotiffWriter:
    """Create a GeoTIFF/COG output handle shaped like a template dataset.

    Parameters
    ----------
    path : Path | str
        The path to the output GeoTIFF.
    variables : list[str]
        The band (variable) names to create.
    ds_like : NetcdfReader | GeotiffReader
        A dataset to use as a spatial template (grid, transform, CRS).
    crs : CRS, optional
        The coordinate reference system; falls back to ``ds_like``'s CRS.
    tile : tuple[int, int], optional
        The ``(height, width)`` COG tile size, which is also the parallel write
        granularity. Defaults to the writer's 512 x 512 tile.

    Returns
    -------
    GeotiffWriter
        The configured writer (call :meth:`GeotiffWriter.start_parallel` before
        writing from worker processes).
    """
    ds = GeotiffWriter(file=path)

    # Derive the cell-centre coordinates from the template geotransform.
    gtf = ds_like.profile.transform
    ny, nx = ds_like.profile.shape
    lons = gtf[0] + gtf[1] * (np.arange(nx) + 0.5)
    lats = gtf[3] + gtf[5] * (np.arange(ny) + 0.5)

    if tile is not None:
        ds.set_block_size(tile_width=tile[1], tile_height=tile[0])
    ds.create_spatial_dims(lats=lats, lons=lons)
    ds.set_spatial_ref(crs if crs is not None else ds_like.profile.crs)
    for var in variables:
        ds.create_spatial_variable(var=var)

    return ds
