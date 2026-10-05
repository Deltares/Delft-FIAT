# cython: language_level=3
"""Shared vector spatial-metadata structure."""

from pyproj.crs import CRS


cdef class VectorProfile:
    """Geospatial metadata of a vector layer.

    Parameters
    ----------
    crs_wkt : str, optional
        The layer CRS as a WKT string.
    crs_org : str, optional
        The CRS authority organisation (e.g. ``"EPSG"``).
    crs_code : int, optional
        The CRS authority code (e.g. ``4326``).
    crs_override : str, optional
        A user-provided CRS (any ``pyproj`` user input) used only when the layer carries
        no CRS of its own.
    bounds : tuple, optional
        The layer envelope as ``(minx, miny, maxx, maxy)``.
    geom_type : int, optional
        The FlatGeobuf ``GeometryType`` code.
    name : str, optional
        The layer name.
    fields : list, optional
        The attribute field names.
    dtypes : list, optional
        The attribute field type codes (FlatGeobuf ``ColumnType``).
    columns : dict, optional
        A mapping of field name to column index.
    size : int, optional
        The feature count.
    """

    def __init__(
        self,
        crs_wkt="",
        crs_org="",
        crs_code=0,
        crs_override=None,
        bounds=None,
        geom_type=None,
        name="",
        fields=None,
        dtypes=None,
        columns=None,
        size=None,
    ):
        self.crs_wkt = crs_wkt
        self.crs_org = crs_org
        self.crs_code = crs_code
        self.crs_override = crs_override
        self.bounds = bounds
        self.geom_type = geom_type
        self.name = name
        self.fields = list(fields) if fields is not None else []
        self.dtypes = list(dtypes) if dtypes is not None else []
        self.columns = dict(columns) if columns is not None else {}
        self.size = size

    def __repr__(self):
        _mem_loc = f"{id(self):#018x}".upper()
        return f"<{self.__class__.__name__} object at {_mem_loc}>"

    @property
    def crs(self):
        """Return the CRS as a :class:`pyproj.crs.CRS`, or ``None``."""
        if self.crs_wkt:
            return CRS.from_user_input(self.crs_wkt)
        if self.crs_org and self.crs_code:
            return CRS.from_user_input(f"{self.crs_org}:{self.crs_code}")
        if self.crs_override:
            return CRS.from_user_input(self.crs_override)
        return None
