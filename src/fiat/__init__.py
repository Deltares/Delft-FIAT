"""FIAT."""

##################################################
# Organisation: Deltares
##################################################
# Author: B.W. Dalmijn
# E-mail: brencodeert@outlook.com
##################################################
# License: MIT license
#
#
#
#
##################################################
import importlib.util
import warnings

from osgeo import osr

osr.UseExceptions()

from .cfg import ConfigReader
from .io import open_csv, open_geom, open_grid
from .main import FIAT
from .models import GeomModel, GridModel
from .version import __version__
