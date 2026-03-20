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

from .cfg import Configurations
from .fio import open_csv, open_geom, open_grid
from .model import GeomModel, GridModel
from .version import __version__

osr.UseExceptions()

__all__ = [
    "Configurations",
    "open_csv",
    "open_geom",
    "open_grid",
    "GeomModel",
    "GridModel",
]
