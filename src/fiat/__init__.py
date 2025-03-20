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
from osgeo import osr

osr.UseExceptions()

from .cfg import Configurations
from .fio import open_csv, open_geom, open_grid
from .models import GeomModel, GridModel
from .version import __version__
