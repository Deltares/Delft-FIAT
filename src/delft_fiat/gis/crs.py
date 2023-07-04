from osgeo import osr


def get_srs_repr(
    srs: osr.SpatialReference,
):
    """Get the spatial reference representation

    Parameters
    ----------
    srs : osr.SpatialReference
        Spatial reference

    Returns
    -------
    str
        Spatial reference representation
    """

    # Get the authority code and name
    _auth_c = srs.GetAuthorityCode(None)
    _auth_n = srs.GetAuthorityName(None)

    # Check if the spatial reference has an authority code
    if _auth_c is None or _auth_n is None:
        return srs.ExportToProj4()

    return f"{_auth_n}:{_auth_c}"


class CRS:
    """Coordinate Reference System"""

    def __init__(
        self,
        srs: osr.SpatialReference,
    ):
        """Constructor

        Parameters
        ----------
        srs : osr.SpatialReference
            Spatial reference
        """
        raise NotImplementedError("CRS __init__ is not implemented yet")

    def __del__(self):
        raise NotImplementedError("CRS __del__ is not implemented yet")

    def __eq__(self):
        raise NotImplementedError("CRS __eq__ is not implemented yet")

    @classmethod
    def from_user_input(
        cls,
        user_input: str,
    ):
        """Create a CRS from user input

        Parameters
        ----------
        user_input : str
            User input

        Returns
        -------
        CRS
            Coordinate reference system
        """

        return cls()
