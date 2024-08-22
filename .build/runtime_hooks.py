"""Runtime hooks for pyinstaller."""

import os
import sys
from pathlib import Path

# Path to executable
cwd = Path(sys.executable).parent

# Paths to libaries
os.environ["PROJ_LIB"] = str(Path(cwd, "bin", "share"))
sys.path.append(str(Path(cwd, "bin", "share")))
