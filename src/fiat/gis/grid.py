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
    dst_crs: str,
    dst_gtf: list | tuple = None,
    dst_width: int = None,
    dst_height: int = None,
    out_dir: Path | str = None,
    resample: int = 0,
) -> object:
    """Reproject (warp) a grid.

    Parameters
    ----------
    gs : GridSource
        Input object.
    dst_crs : str
        Coodinates reference system (projection). An accepted format is: `EPSG:3857`.
    dst_gtf : list | tuple, optional
        The geotransform of the warped dataset. Must be defined in the same
        coordinate reference system as dst_crs. When defined, its only used when
        both 'dst_width' and 'dst_height' are defined.
    dst_width : int, optional
        The width of the warped dataset in pixels.
    dst_height : int, optional
        The height of the warped dataset in pixels.
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
    out_srs.SetFromUserInput(dst_crs)
    out_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

    warp_kw = {}
    if all([item is not None for item in [dst_gtf, dst_width, dst_height]]):
        warp_kw.update(
            {
                "xRes": dst_gtf[1],
                "yRes": dst_gtf[5],
                "outputBounds": (
                    dst_gtf[0],
                    dst_gtf[3] + dst_gtf[5] * dst_height,
                    dst_gtf[0] + dst_gtf[1] * dst_width,
                    dst_gtf[3],
                ),
                "width": dst_width,
                "height": dst_height,
            }
        )

    dst_src = gdal.Warp(
        str(fname_int),
        gs.src,
        srcSRS=gs.get_srs(),
        dstSRS=out_srs,
        resampleAlg=resample,
        **warp_kw,
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

    os.unlink(fname_int)

    return open_grid(fname, **_gs_kwargs)
