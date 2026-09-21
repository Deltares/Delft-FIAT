"""Runtime hooks for pyinstaller."""

import os
import sys
from pathlib import Path

# Path to executable
cwd = Path(sys.executable).parent

# Paths to libaries/ data
os.environ["GDAL_DATA"] = str(Path(cwd, "bin", "share", "gdal"))
os.environ["GDAL_DRIVER_PATH"] = str(Path(cwd, "bin", "gdalplugins"))
# Newer versions of GDAL and PROJ
os.environ["PROJ_DATA"] = str(Path(cwd, "bin", "share", "proj"))
# Older versions of GDAL and PROJ
os.environ["PROJ_LIB"] = str(Path(cwd, "bin", "share", "proj"))
# Append to path
sys.path.append(str(Path(cwd, "bin", "share")))
