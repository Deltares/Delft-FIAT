# cython: language_level=3
"""Shared raster spatial-metadata structure."""

import numpy as np
from pyproj.crs import CRS

# Supported file extensions
GRID_EXTENSIONS = {".nc", ".tif", ".tiff"}

cdef class GridProfile:
    """Geospatial metadata of a raster.

    Parameters
    ----------
    xvals : array-like, optional
        The 1D x (longitude) coordinate values of the cell centres.
    yvals : array-like, optional
        The 1D y (latitude) coordinate values of the cell centres.
    crs_wkt : str, optional
        The coordinate reference system as a WKT (or any ``pyproj`` user-input) string.

    Attributes
    ----------
    crs_wkt : str | None
        The stored CRS string (WKT or other ``pyproj`` user input).
    xvals, yvals : np.ndarray | None
        The 1D coordinate values of the cell centres.
    res : tuple[float, float] | None
        The cell resolution as ``(dx, dy)``.
    origin : tuple[float, float] | None
        The grid origin (top-left corner) as ``(x0, y0)``.
    transform : tuple[float, ...] | None
        The affine geotransform ``(x0, dx, 0, y0, 0, dy)``.
    bounds : tuple[float, ...] | None
        The spatial extent as ``(minx, miny, maxx, maxy)``.
    shape : tuple[int, int] | None
        The raster shape as ``(ny, nx)``.
    shape_xy : tuple[int, int] | None
        The raster shape as ``(nx, ny)``.
    """

    def __init__(self, xvals=None, yvals=None, crs_wkt=None):
        self.crs_wkt = crs_wkt
        self.xvals = None if xvals is None else np.asarray(xvals)
        self.yvals = None if yvals is None else np.asarray(yvals)
        self.res = None
        self.origin = None
        self.transform = None
        self.bounds = None
        self.shape = None
        self.shape_xy = None

        if self.xvals is not None and self.yvals is not None:
            self.derive_from_dims()

    def __repr__(self):
        _mem_loc = f"{id(self):#018x}".upper()
        return f"<{self.__class__.__name__} object at {_mem_loc}>"

    @property
    def crs(self):
        """Return the CRS as a :class:`pyproj.crs.CRS`, or ``None``."""
        if self.crs_wkt is None:
            return None
        return CRS.from_user_input(self.crs_wkt)

    cpdef derive_from_dims(self):
        """Derive the spatial metadata from the ``x``/``y`` coordinate arrays."""
        xs = self.xvals
        ys = self.yvals

        # The resolution
        dx = float(np.diff(xs).mean())
        dy = float(np.diff(ys).mean())
        self.res = (dx, dy)

        # The origin (top-left corner of the first cell)
        x0 = float(xs[0] - dx / 2)
        y0 = float(ys[0] - dy / 2)
        self.origin = (x0, y0)

        # The affine geotransform
        self.transform = (x0, dx, 0.0, y0, 0.0, dy)

        # The shape
        nx = int(xs.shape[0])
        ny = int(ys.shape[0])
        self.shape = (ny, nx)
        self.shape_xy = (nx, ny)

        # The bounds
        xmin, xmax = sorted([x0, x0 + dx * nx])
        ymin, ymax = sorted([y0 + dy * ny, y0])
        self.bounds = (xmin, ymin, xmax, ymax)
