"""Spec file for building fiat."""

import inspect
import sys
import time
from pathlib import Path

from fiat.util import generic_folder_check

# Pre build event setup
app_name = "fiat"
mode = "Release"
sys.setrecursionlimit(5000)

# Some general information
_file = Path(inspect.getfile(lambda: None))
project_root = _file.parents[1]
build_dir = Path(project_root, ".build")

generic_folder_check(Path(project_root, "bin"))

# Set the build time for '--version' usage
now = time.localtime(time.time())
FIAT_BUILD_TIME = time.strftime('%Y-%m-%dT%H:%M:%S UTC%z', now)
with open(Path(build_dir, "fiat_build_time.py"), "w") as _w:
    _w.write(f'BUILD_TIME = "{FIAT_BUILD_TIME}"')

# Build event
a = Analysis(
    [Path(project_root, "src/fiat/cli/main.py")],
    pathex=[Path(build_dir), Path(project_root, "src")],
    binaries=[],
    datas=[],
    hiddenimports=["fiat_build_time"],
    hookspath=[build_dir.as_posix()],
    hooksconfig={},
    runtime_hooks=[Path(build_dir, 'runtime_hooks.py')],
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
