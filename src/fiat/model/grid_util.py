"""Grid model utility."""

from itertools import product

from fiat.check import check_exp_grid_fn
from fiat.fio import GridIO
from fiat.model.util import get_band_names
from fiat.struct.container import ExposureGridMeta, HazardMeta, VulnerabilityMeta


def get_exposure_meta(
    exposure: GridIO,
    hazard_meta: HazardMeta,
    vulnerability_meta: VulnerabilityMeta,
) -> ExposureGridMeta:
    """Simple method for sorting out the exposure grid meta."""  # noqa : D401
    # Check if all impact functions are correct
    fn_list = [item.get_metadata_item("fn") for item in exposure]
    check_exp_grid_fn(
        fn_list=fn_list,
        fn_available=vulnerability_meta.fn_list,
    )
    # Get the new band names
    names = get_band_names(exposure)
    new = ["_".join(c) for c in product(names, hazard_meta.names)]

    # Set up the meta
    meta = ExposureGridMeta(
        fn_list=fn_list,
        nb=len(new),
        new=new,
    )
    return meta
