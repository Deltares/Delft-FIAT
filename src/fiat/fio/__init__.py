"""The I/O module of FIAT."""

from osgeo import gdal

from .buffer import *
from .fopen import *
from .geom import *
from .grid import *

gdal.AllRegister()
