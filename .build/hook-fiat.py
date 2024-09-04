"""Build hook for FIAT."""

import glob
import os
import sys
from pathlib import Path

from osgeo.gdal import __version__ as gdal_version
from packaging.version import Version
from PyInstaller.compat import is_conda, is_win
from PyInstaller.utils.hooks import logger
from PyInstaller.utils.hooks.conda import (
    distribution,
)

datas = []

if hasattr(sys, "real_prefix"):  # check if in a virtual environment
    root_path = sys.real_prefix
else:
    root_path = sys.prefix

if is_conda and Version(gdal_version) >= Version("3.9.1"):
    plugin = distribution("libgdal-netcdf")

    # Look for all the plugins
    plugin_dir = Path(root_path, plugin.files[0].parent)
    all_plugins = glob.glob(Path(plugin_dir, "*").as_posix())

    # Append the data
    datas += list(map(lambda path: (path, "./gdalplugins"), all_plugins))

# Sort out the proj database
src_proj = None
if "PROJ_DATA" in os.environ:
    src_proj = os.environ["PROJ_DATA"]
elif "PROJ_LIB" in os.environ:
    src_proj = os.environ["PROJ_LIB"]

# Default check based on known directories
if src_proj is None:
    if is_win:
        src_proj = os.path.join(root_path, "Library", "share", "proj")
    else:  # both linux and darwin
        src_proj = os.path.join(root_path, "share", "proj")
    if not os.path.isdir(src_proj):
        src_proj = None
        logger.warning("Proj data was not found.")

if src_proj is not None:
    datas.append((src_proj, "./share"))
