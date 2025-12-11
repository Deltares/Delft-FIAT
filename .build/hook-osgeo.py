"""Build hook for osgeo."""
# ------------------------------------------------------------------
# Copyright (c) 2020 PyInstaller Development Team.
#
# This file is distributed under the terms of the GNU General Public
# License (version 2.0 or later).
#
# The full license is available in LICENSE, distributed with
# this software.
#
# SPDX-License-Identifier: GPL-2.0-or-later
# ------------------------------------------------------------------

import os
import sys

from PyInstaller.compat import is_darwin, is_win
from PyInstaller.log import logger

# Location of the binary
if hasattr(sys, "real_prefix"):  # check if in a virtual environment
    root_path = sys.real_prefix
else:
    root_path = sys.prefix

# Check the current state of the data
datas = []

src_gdal = None
# Do the same for gdal data
if src_gdal is None:
    if is_win:
        src_gdal = os.path.join(root_path, "Library", "share", "gdal")
        if not os.path.exists(src_gdal):
            src_gdal = os.path.join(root_path, "Library", "data")
    else:  # both linux and darwin
        src_gdal = os.path.join(root_path, "share", "gdal")
    if not os.path.isdir(src_gdal):
        src_gdal = None
        logger.warning("GDAL data was not found.")

if src_gdal is not None:
    datas.append((src_gdal, "./share/gdal"))

# Hidden dependencies
if src_gdal is not None:
    # if `proj.4` is present, it provides additional functionalities
    if is_win:
        proj4_lib = os.path.join(root_path, "proj.dll")
    elif is_darwin:
        proj4_lib = os.path.join(root_path, "lib", "libproj.dylib")
    else:  # assumed linux-like settings
        proj4_lib = os.path.join(root_path, "lib", "libproj.so")

    if os.path.exists(proj4_lib):
        binaries = [(proj4_lib, ".")]
