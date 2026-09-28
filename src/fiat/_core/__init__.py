"""Compiled (Cython) acceleration core for FIAT.

This subpackage contains the mandatory compiled extension modules that
accelerate the hottest numeric paths of the model workers. The public Python
API of FIAT imports from here directly; there is no pure-Python fallback.
"""

from fiat._core._interp import Interp1D
from fiat._core._overlay import cell_mask, clip_masked
from fiat._core._zonal import zonal_reduce

__all__ = ["Interp1D", "cell_mask", "clip_masked", "zonal_reduce"]
