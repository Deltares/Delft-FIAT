"""Grid model utility."""

from collections import deque
from itertools import product

from fiat.check import check_exp_grid_fn, check_grid_exact
from fiat.fio import Dataset
from fiat.gis import grid
from fiat.struct.container import (
    ExposureGridMeta,
    HazardMeta,
    RunMeta,
    VulnerabilityMeta,
)
from fiat.util import EAD, FN, TOTAL, get_srs_repr


def get_exposure_meta(
    exposure: Dataset,
    run_meta: RunMeta,
    hazard_meta: HazardMeta,
    vulnerability_meta: VulnerabilityMeta,
) -> ExposureGridMeta:
    """Simple method for sorting out the exposure grid meta."""  # noqa : D401
    # Check if all impact functions are correct
    fn_list = [item.get_attr(FN) for item in exposure]
    check_exp_grid_fn(
        fn_list=fn_list,
        fn_available=vulnerability_meta.fn_list,
    )

    # Get the new band names
    new = ["_".join(c) for c in product(exposure.names, hazard_meta.ids)]
    new += [f"{TOTAL}_{idi}" for idi in hazard_meta.ids]

    # Setup from indices
    indices_new = [
        [s + hazard_meta.length * i for i in range(exposure.size)]
        for s in range(hazard_meta.length)
    ]
    indices_total = list(
        range(
            hazard_meta.length * exposure.size,
            hazard_meta.length * exposure.size + hazard_meta.length,
        )
    )
    index_ead = None
    if run_meta.risk:
        index_ead = len(new)
        new += [EAD]

    # Set up the meta
    meta = ExposureGridMeta(
        fn_list=fn_list,
        index_ead=index_ead,
        indices_new=indices_new,
        indices_total=indices_total,
        nb=len(new),
        new=new,
    )
    return meta


def equal_grid(
    gs1: Dataset,
    gs2: Dataset,
    first: bool = True,
) -> deque[Dataset] | tuple[Dataset]:
    """Ensure homogeneity between two grids.

    Parameters
    ----------
    gs1 : Dataset
        The first dataset.
    gs2 : Datset
        The second dataset.
    first : bool, optional
        Whether to make the second equal to the first of vice versa, by default True.
    """
    equal = check_grid_exact(gs1, gs2)
    if equal:
        return gs1, gs2

    # When not equal resample one of the two
    gss: deque[Dataset] = deque([gs1, gs2])
    # Rotate based on the boolean
    gss.rotate(first)

    # Reproject the data
    gs_out = grid.reproject(
        gss[0],
        dst_srs=get_srs_repr(gss[1].srs),
        dst_gtf=gss[1].transform,
        dst_width=gss[1].shape_xy[0],
        dst_height=gss[1].shape_xy[1],
    )

    # Set the output dataset in the deque
    gss[0] = gs_out
    # Re-shift it
    gss.rotate(first)

    # Return the output
    return gss
