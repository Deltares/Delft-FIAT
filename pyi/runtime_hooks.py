"""Runtime hooks for pyinstaller."""

import os
import sys
from pathlib import Path

# Path to executable
cwd = Path(sys.executable).parent

# Paths to libaries
os.environ["GDAL_DRIVER_PATH"] = Path(cwd, "bin", "gdalplugins").as_posix()
# Newer versions of GDAL and PROJ
os.environ["PROJ_DATA"] = str(Path(cwd, "bin", "share"))
# Older versions of GDAL and PROJ
os.environ["PROJ_LIB"] = str(Path(cwd, "bin", "share"))
# Append to path
sys.path.append(str(Path(cwd, "bin", "share")))
