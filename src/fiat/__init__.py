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
from .main import FIAT
from .version import __version__

# if not importlib.util.find_spec("PySide2"):
#     warnings.warn("PySide2 is not installed in \
# this environment -> ui is not callable")
# else:
#     from .gui import *
