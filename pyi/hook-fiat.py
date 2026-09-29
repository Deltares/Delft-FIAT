"""Build hook for FIAT."""

import os
import sys

from PyInstaller.compat import is_win
from PyInstaller.utils.hooks import logger

datas = []

if hasattr(sys, "real_prefix"):  # check if in a virtual environment
    root_path = sys.real_prefix
else:
    root_path = sys.prefix

# Sort out the proj database (needed by pyproj)
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
    datas.append((src_proj, "./share/proj"))
