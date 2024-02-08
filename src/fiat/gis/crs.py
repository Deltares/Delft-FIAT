"""Custom CRS define."""

from osgeo import osr


def get_srs_repr(
    srs: osr.SpatialReference,
) -> str:
    """_summary_."""
    _auth_c = srs.GetAuthorityCode(None)
    _auth_n = srs.GetAuthorityName(None)

    if _auth_c is None or _auth_n is None:
        return srs.ExportToProj4()

    return f"{_auth_n}:{_auth_c}"


class CRS:
    """_summary_."""

    def __init__(
        self,
        srs: osr.SpatialReference,
    ):
        pass

    def __del__(self):
        pass

    def __eq__(self):
        pass

    @classmethod
    def from_user_input(
        cls,
        user_input: str,
    ):
        """_summary_."""
        return cls()
