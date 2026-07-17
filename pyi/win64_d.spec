from fiat.util import generic_directory_check

import os
import sys
from pathlib import Path

#Pre build event setup
app_name = "fiat"
sys.setrecursionlimit(5000)
generic_directory_check("../bin")

cwd = Path.cwd()
env_path =  os.path.dirname(sys.executable)
mode = "Debug"

proj = Path(os.environ["PROJ_LIB"])

binaries = [
    (Path(proj, 'proj.db'), './share'),
]

# Build event
a = Analysis(
    ["../src/fiat/cli/main.py"],
    pathex=["../src", Path(env_path, "lib/site-packages")],
    binaries=binaries,
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['runtime_hooks.py'],
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
    [('v', None, 'OPTION')],
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
