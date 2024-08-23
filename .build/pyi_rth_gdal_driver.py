"""
Pyinstaller hook that sets mandatory env var.

Based on https://github.com/conda-forge/gdal-feedstock/blob/main/recipe/scripts/activate.sh
"""

import os
import sys

# Installing `osgeo` Conda packages with plugins requires to set `GDAL_DRIVER_PATH`

is_win = sys.platform.startswith("win")
if is_win:
    gdal_plugins = os.path.join(sys._MEIPASS, "share", "gdalplugins")
    if not os.path.exists(gdal_plugins):
        gdal_plugins = os.path.join(sys._MEIPASS, "Library", "lib", "gdalplugins")
        # last attempt, check if one of the required file is in the generic folder Library/data
        if not os.path.exists(os.path.join(gdal_plugins, "gcs.csv")):
            gdal_plugins = os.path.join(sys._MEIPASS, "Library", "lib")

else:
    gdal_plugins = os.path.join(sys._MEIPASS, "lib", "gdalplugins")

if os.path.exists(gdal_plugins):
    os.environ["GDAL_DRIVER_PATH"] = gdal_plugins

print(f"GDAL_DRIVER_PATH = {gdal_plugins}")
print("contents:")
print(os.listdir(gdal_plugins))
