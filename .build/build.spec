from fiat.util import generic_folder_check

import inspect
import os
import sys
from pathlib import Path

#Pre build event setup
app_name = "fiat"
sys.setrecursionlimit(5000)

_file = Path(inspect.getfile(lambda: None))
cwd = _file.parent
env_path =  os.path.dirname(sys.executable)
generic_folder_check(Path(cwd, "../bin"))
mode = "Release"

proj = Path(os.environ["PROJ_LIB"])

binaries = [
    (Path(proj, 'proj.db'), './share'),
]

# Build event
a = Analysis(
    [Path(cwd, "../src/fiat/cli/main.py")],
    pathex=[Path(cwd, "../src"), Path(env_path, "lib/site-packages")],
    binaries=binaries,
    datas=[],
    hiddenimports=["fiat.math"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[Path(cwd, 'runtime_hooks.py')],
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
