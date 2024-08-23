from fiat.util import generic_folder_check

import inspect
import os
import sys
from pathlib import Path, PurePath

#Pre build event setup
app_name = "fiat"
sys.setrecursionlimit(5000)

_file = Path(inspect.getfile(lambda: None))

# Get project root directory
project_root = _file.parents[1].absolute()

build_dir = project_root / ".build"
env_path =  Path(os.getenv("CONDA_PREFIX"))

# check if bin folder is in build dir.
generic_folder_check(build_dir / "bin")
mode = "Release"

# Find proj folder
proj = Path(os.environ.get("PROJ_LIB", env_path / "share" / "proj"))
# Find gdal plugins folder
is_win = sys.platform.startswith("win")
if is_win:
    gdal_plugins_default_directory = PurePath("Library") / "lib" / "gdalplugins"
else:
    gdal_plugins_default_directory = PurePath("lib") / "gdalplugins"

gdal_plugins = Path(os.environ.get("GDAL_DRIVER_PATH", Path(env_path) / gdal_plugins_default_directory))

binaries = [
    (Path(proj, 'proj.db'), "./share"),
    (Path(gdal_plugins), str(gdal_plugins_default_directory)),
]

# Build event
a = Analysis(
    [Path(project_root, "src/fiat/cli/main.py")],
    pathex=[Path(project_root, "src")],
    binaries=binaries,
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[
        Path(build_dir, "runtime_hooks.py"),
        Path(build_dir, "pyi_rth_gdal_driver.py"),
    ],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(
    a.pure,
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    icon="NONE",
    exclude_binaries=True,
    name=app_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory='bin',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=mode,
)
