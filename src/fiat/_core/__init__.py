"""Compiled (Cython) acceleration core for FIAT.

This subpackage contains the compiled extension modules that accelerate the
hottest numeric paths of the model workers. The public Python API of FIAT
imports from here directly.
"""

from ._interp import Interp1D
from ._overlay import cell_mask, clip_masked
from ._zonal import zonal_reduce

__all__ = ["Interp1D", "cell_mask", "clip_masked", "zonal_reduce"]
