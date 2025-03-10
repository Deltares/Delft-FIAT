"""Custom CRS define."""

from osgeo import osr


def get_srs_repr(
    srs: osr.SpatialReference,
) -> str:
    """Get a representation of a spatial reference system object.

    Parameters
    ----------
    srs : osr.SpatialReference
        Spatial reference system.

    Returns
    -------
    str
        Representing string.
    """
    if srs is None:
        raise ValueError("'srs' can not be 'None'.")
    _auth_c = srs.GetAuthorityCode(None)
    _auth_n = srs.GetAuthorityName(None)

    if _auth_c is None or _auth_n is None:
        return srs.ExportToProj4()

    return f"{_auth_n}:{_auth_c}"
