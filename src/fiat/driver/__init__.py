"""The I/O module of FIAT."""

from osgeo import gdal

from .buffer import *
from .csv import *
from .geom import *
from .netcdf import *

gdal.AllRegister()
