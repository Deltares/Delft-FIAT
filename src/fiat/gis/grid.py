"""Only raster methods for FIAT."""

from pathlib import Path

from osgeo import gdal, osr

from fiat.fio import GridIO, open_grid
from fiat.struct import GridBand
from fiat.util import NOT_IMPLEMENTED


def clip(
    band: GridBand,
    gtf: tuple,
    idx: tuple,
):
    """Clip a grid.

    Parameters
    ----------
    band : gdal.Band
        _description_
    gtf : tuple
        _description_
    idx : tuple
        _description_
    """
    raise NotImplementedError(NOT_IMPLEMENTED)


def reproject(
    gs: GridIO,
    dst_srs: str,
    dst_gtf: list | tuple = None,
    dst_width: int = None,
    dst_height: int = None,
    out_dir: Path | str = None,
    resample: int = 0,
) -> object:
    """Reproject (warp) a grid.

    Parameters
    ----------
    gs : GridIO
        Input object.
    dst_srs : str
        Coodinates reference system (projection). An accepted format is: `EPSG:3857`.
    dst_gtf : list | tuple, optional
        The geotransform of the warped dataset. Must be defined in the same
        coordinate reference system as dst_srs. When defined, its only used when
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
    GridIO
        Output object. A lazy reading of the just creating raster file.
    """
    # Set some kwargs before moving on
    _gs_kwargs = {
        "chunk": gs.chunk,
    }

    if not Path(str(out_dir)).is_dir():
        out_dir = gs.path.parent

    fname = Path(out_dir, f"{gs.path.stem}_repr.tif")

    out_srs = osr.SpatialReference()
    out_srs.SetFromUserInput(dst_srs)
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
                # "width": dst_width,
                # "height": dst_height,
            }
        )

    _ = gdal.Warp(
        str(fname),
        gs.src,
        srcSRS=gs.srs,
        dstSRS=out_srs,
        resampleAlg=resample,
        **warp_kw,
    )

    out_srs = None

    gs.close()
    return open_grid(fname, **_gs_kwargs)
