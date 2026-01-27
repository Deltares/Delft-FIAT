"""The FIAT model workers."""

from typing import Callable

import numpy as np

from fiat.check import check_hazard_identifier, check_hazard_rp, check_hazard_types
from fiat.fio import GridIO
from fiat.method.ead import fn_density
from fiat.struct import Table
from fiat.struct.container import HazardMeta, VulnerabilityMeta
from fiat.typing import MethodsProtocol
from fiat.util import deter_dec

GEOM_DEFAULT_CHUNK = 50000
GRID_PREFER = {
    False: "hazard",
    True: "exposure",
}


def get_band_names(
    ds: GridIO,
) -> list:
    """Determine the names of the bands.

    If the bands do not have any names of themselves,
    they will be set to a default.
    """
    names = []
    for idx, band in enumerate(ds):
        name = band.name
        names.append(name or f"band{idx+1}")

    return names


def get_hazard_meta(hazard: GridIO, risk: bool, method: MethodsProtocol) -> HazardMeta:
    """Obtain some metadata from the hazard data."""
    # Get the types from the metadata
    types = [band.get_metadata_item("type") for band in hazard]
    # Check the typing
    indices_type = check_hazard_types(
        types,
        method.TYPES,
    )

    # Get the identifiers:
    identifier = None if not risk else "rp"
    ids = [str(idx + 1) for idx, _ in enumerate(indices_type[0])]
    ids_list = [ids] * len(indices_type)

    # If identifier is not None
    if identifier is not None:
        ids, ids_list = check_hazard_identifier(
            [band.get_metadata_item(identifier) for band in hazard],
            indices_type=indices_type,
        )

    # Look at risk specific info
    d = None
    rp = None
    if risk:
        rp = check_hazard_rp(ids)
        d = fn_density(rp)

    # Set the grouped indices
    indices_run = [
        [indices_type[idx][item.index(idi)] for idx, item in enumerate(ids_list)]
        for idi in ids
    ]

    # Fill in the meta
    meta = HazardMeta(
        density=d,
        ids=ids,
        indices_run=indices_run,
        indices_type=indices_type,
        length=len(ids),
        rp=rp,
        risk=risk,
        type=method.NAME,
        type_length=len(method.TYPES),
    )
    return meta


def get_vulnerability_meta(
    vulnerability: Table,
) -> VulnerabilityMeta:
    """Obtain some metadata from the vulnerability data."""
    imin = min(vulnerability.index)
    imax = max(vulnerability.index)
    sigdec = deter_dec((imax - imin) / len(vulnerability.index))
    meta = VulnerabilityMeta(
        fn_list=vulnerability.columns,
        min=imin,
        max=imax,
        sigdec=sigdec,
    )
    return meta


def vectorize_function(
    fn: Callable,
    skip: int,
    dtype: type = np.float32,
) -> Callable:
    """Vectorize a function simply."""
    na = fn.__code__.co_argcount
    excluced = set(fn.__code__.co_varnames[skip:na])
    fn_vec = np.vectorize(fn, otypes=[dtype], excluded=excluced)
    return fn_vec
