"""
Analysis hook for fiat installation.

Helps finding different dependencies for PyInstaller.
"""

import os
import sys

from PyInstaller.compat import is_conda, is_win
from PyInstaller.utils.hooks.conda import (
    Distribution,
    distribution,
)

datas = []

if hasattr(sys, "real_prefix"):  # check if in a virtual environment
    root_path = sys.real_prefix
else:
    root_path = sys.prefix

if is_conda:
    netcdf_dist: Distribution = distribution("libgdal-netcdf")
    # append netcdf files to datas
    datas += list(
        map(
            lambda path: (os.path.join(root_path, path), str(path.parent)),
            netcdf_dist.files,
        )
    )
    # a runtime hook defines the path for `GDAL_DRIVER_PATH`

# - conda-specific
if is_win:
    tgt_proj_data = os.path.join("Library", "share", "proj")
    src_proj_data = os.path.join(root_path, "Library", "share", "proj")

else:  # both linux and darwin
    tgt_proj_data = os.path.join("share", "proj")
    src_proj_data = os.path.join(root_path, "share", "proj")

if is_conda:
    if os.path.exists(src_proj_data):
        datas.append((src_proj_data, tgt_proj_data))
    else:
        from PyInstaller.utils.hooks import logger

        logger.warning("Datas for proj not found at:\n{}".format(src_proj_data))
    # A runtime hook defines the path for `PROJ_LIB`
