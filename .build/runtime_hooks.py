"""Runtime hooks for pyinstaller."""

import os
import sys
from pathlib import Path

# Path to executable
base = Path(sys.executable).parent
bin_dir = Path(base, "bin")

# Paths to libaries/ data
os.environ["GDAL_DATA"] = str(Path(bin_dir, "share", "gdal"))
os.environ["GDAL_DRIVER_PATH"] = str(Path(bin_dir, "gdalplugins"))
# Newer versions of GDAL and PROJ
os.environ["PROJ_DATA"] = str(Path(bin_dir, "share", "proj"))
# Older versions of GDAL and PROJ
os.environ["PROJ_LIB"] = str(Path(bin_dir, "share", "proj"))
# Append to path
sys.path.append(str(Path(bin_dir, "osgeo")))
