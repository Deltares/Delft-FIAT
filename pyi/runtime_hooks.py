"""Runtime hooks for pyinstaller."""

import os
import sys
from pathlib import Path

# Path to executable
cwd = Path(sys.executable).parent

# Paths to libaries/ data
# PROJ data (needed by pyproj)
os.environ["PROJ_DATA"] = str(Path(cwd, "bin", "share", "proj"))
# Older versions of PROJ
os.environ["PROJ_LIB"] = str(Path(cwd, "bin", "share", "proj"))
# Append to path
sys.path.append(str(Path(cwd, "bin", "share")))
