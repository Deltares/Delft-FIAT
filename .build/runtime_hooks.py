"""Runtime hooks for pyinstaller."""

import os
import sys
from pathlib import Path

cwd = Path(sys.executable).parent

os.environ["PROJ_LIB"] = str(Path(cwd, "bin", "share"))
sys.path.append(str(Path(cwd, "bin", "share")))
