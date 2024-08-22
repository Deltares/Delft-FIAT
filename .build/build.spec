"""Spec file for building fiat."""

import importlib
import inspect
import os
import sys
import time
from pathlib import Path

from fiat.util import generic_folder_check

# Pre build event setup
app_name = "fiat"
sys.setrecursionlimit(5000)

# Some general information
_file = Path(inspect.getfile(lambda: None))
cwd = _file.parent
env_path =  os.path.dirname(sys.executable)
generic_folder_check(Path(cwd, "../bin"))
mode = "Release"
# Set the build time for '--version' usage
now = time.localtime(time.time())
FIAT_BUILD_TIME = time.strftime('%Y-%m-%dT%H:%M:%S UTC%z', now)
with open(Path(cwd, "fiat_build_time.py"), "w") as _w:
    _w.write(f'BUILD_TIME = "{FIAT_BUILD_TIME}"')

# Get the location of the proj database
proj = Path(os.environ["PROJ_LIB"])

# Add to the list of binaries (although its a database)
binaries = [
    (Path(proj, 'proj.db'), './share'),
]

# Build event
a = Analysis(
    [Path(cwd, "../src/fiat/cli/main.py")],
    pathex=[Path(cwd), Path(cwd, "../src")],
    binaries=binaries,
    datas=[],
    hiddenimports=["fiat_build_time"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[Path(cwd, 'runtime_hooks.py')],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

# Whatever the fuck this precisely does..
pyz = PYZ(
    a.pure,
)

# Arguments for the executable
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

# Collect all binaries and libraries
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=mode,
)
