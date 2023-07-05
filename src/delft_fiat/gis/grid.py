from delft_fiat.io import open_grid

import gc
import os
from osgeo import gdal, osr
from pathlib import Path


def reproject(
    gs: "GridSource",
    crs: str,
    out: str = None,
    resample: int = 0,
) -> object:
    """_summary_

    Parameters
    ----------
    gs : GridSource
        _description_
    crs : str
        _description_

    Returns
    -------
    object
        _description_
    """

    _gs_kwargs = gs._kwargs

    if not Path(str(out)).is_dir():
        out = gs.path.parent

    fname_int = Path(out, f"{gs.path.stem}_repr_fiat.tif")
    fname = Path(out, f"{gs.path.stem}_repr_fiat{gs.path.suffix}")

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
    tr_src = gdal.Translate(str(fname), dst_src)
    tr_src = None
    dst_src = None
    gc.collect()

    os.remove(fname_int)

    return open_grid(fname, **_gs_kwargs)
