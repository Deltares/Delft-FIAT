"""Only raster methods for FIAT."""

import gc
import os
from pathlib import Path

from osgeo import gdal, osr

from fiat.io import Grid, GridSource, open_grid


def clip(
    band: Grid,
    gtf: tuple,
    idx: tuple,
):
    """_summary_.

    Parameters
    ----------
    band : gdal.Band
        _description_
    gtf : tuple
        _description_
    idx : tuple
        _description_
    """
    pass


def reproject(
    gs: GridSource,
    crs: str,
    out_dir: Path | str = None,
    resample: int = 0,
) -> object:
    """Reproject (warp) a grid.

    Parameters
    ----------
    gs : GridSource
        Input object.
    crs : str
        Coodinates reference system (projection). An accepted format is: `EPSG:3857`.
    out_dir : Path | str, optional
        Output directory. If not defined, if will be inferred from the input object.
    resample : int, optional
        Resampling method during warping. Interger corresponds with a resampling
        method defined by GDAL. For more information: click \
[here](https://gdal.org/api/gdalwarp_cpp.html#_CPPv415GDALResampleAlg).

    Returns
    -------
    GridSource
        Output object. A lazy reading of the just creating raster file.
    """
    _gs_kwargs = gs._kwargs

    if not Path(str(out_dir)).is_dir():
        out_dir = gs.path.parent

    fname_int = Path(out_dir, f"{gs.path.stem}_repr_fiat.tif")
    fname = Path(out_dir, f"{gs.path.stem}_repr_fiat{gs.path.suffix}")

    out_srs = osr.SpatialReference()
    out_srs.SetFromUserInput(crs)
    out_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

    dst_src = gdal.Warp(
        str(fname_int),
        gs.src,
        dstSRS=out_srs,
        resampleAlg=resample,
    )

    out_srs = None

    if gs.path.suffix == ".tif":
        gs.close()
        dst_src = None
        return open_grid(fname_int)

    gs.close()
    gdal.Translate(str(fname), dst_src)
    dst_src = None
    gc.collect()

    os.remove(fname_int)

    return open_grid(fname, **_gs_kwargs)
