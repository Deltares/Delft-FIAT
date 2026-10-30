"""Grid model utility."""

from collections import deque

from fiat.check import check_grid_exact
from fiat.driver import NetcdfReader
from fiat.gis import grid
from fiat.util import HAZARD, get_crs_repr


def equal_grid(
    gs1: NetcdfReader,
    gs2: NetcdfReader,
    base: str = HAZARD,
) -> deque[NetcdfReader] | tuple[NetcdfReader]:
    """Ensure homogeneity between two grids.

    Parameters
    ----------
    gs1 : NetcdfReader
        The first dataset.
    gs2 : Datset
        The second dataset.
    base : str, optional
        Which dataset is the base for the geotransfrom, extent etc., by default True.
    """
    equal = check_grid_exact(gs1, gs2)
    if equal:
        return gs1, gs2

    # When not equal resample one of the two
    gss: deque[NetcdfReader] = deque([gs1, gs2])
    # Rotate based on the boolean
    gss.rotate(base == HAZARD)

    # Reproject the data
    gs_out = grid.reproject(
        gss[0],
        dst_crs=get_crs_repr(gss[1].profile.crs),
        dst_gtf=gss[1].profile.transform,
        dst_width=gss[1].profile.shape_xy[0],
        dst_height=gss[1].profile.shape_xy[1],
    )

    # Set the output dataset in the deque
    gss[0] = gs_out
    # Re-shift it
    gss.rotate(base == HAZARD)

    # Return the output
    return gss
