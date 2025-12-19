"""The FIAT model workers."""

from fiat.check import check_hazard_rp
from fiat.fio import GridIO
from fiat.methods.ead import fn_density
from fiat.struct import Table
from fiat.struct.container import HazardMeta, VulnerabilityMeta
from fiat.util import deter_dec

GEOM_DEFAULT_CHUNK = 50000
GRID_PREFER = {
    False: "hazard",
    True: "exposure",
}


def get_band_names(
    obj: GridIO,
) -> list:
    """Determine the names of the bands.

    If the bands do not have any names of themselves,
    they will be set to a default.
    """
    names = []
    for n in range(obj.size):
        name = obj.get_band_name(n)
        if not name:
            names.append(f"band{n+1}")
            continue
        names.append(name)

    return names


def get_hazard_meta(
    hazard: GridIO,
    risk: bool,
) -> HazardMeta:
    """Obtain some metadata from the hazard data."""
    names = get_band_names(hazard)

    # Look at risk specific info
    d = None
    rp = None
    if risk:
        rp = [hazard[idx].get_metadata_item("rp") for idx in range(hazard.size)]
        rp = check_hazard_rp(
            rp,
            None,
            hazard.path,
        )
        d = fn_density(rp)

    # Fill in the meta
    meta = HazardMeta(
        density=d,
        names=names,
        rp=rp,
        risk=risk,
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
        min=imin,
        max=imax,
        sigdec=sigdec,
    )
    return meta
