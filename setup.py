"""Setup for cython extensions."""

import glob
import os
import sys

import numpy
from Cython.Build import cythonize
from Cython.Compiler import Options
from setuptools import Extension, setup

build_dir = "build"
os.makedirs(build_dir, exist_ok=True)
Options.annotate = True

directives_fiat = {
    "boundscheck": False,
    "cdivision": True,
    "language_level": "3",
    "linetrace": False,
    "nonecheck": False,
    "wraparound": False,
}

# Set some global variables
# CURRENT Location
HERE = os.path.dirname(__file__)
# Set all extensions
EXTENSIONS = glob.glob(
    os.path.join("src", "fiat", "**", "*.pyx"),
    recursive=True,
)
# The flatgeobuf source directory
FGB_DIR = os.path.join("src", "fiat", "driver", "fgb")
# The geotiff source directory
GEOTIFF_DIR = os.path.join("src", "fiat", "driver", "geotiff")
# Set the macros
MACROS = [("NPY_NO_DEPRECATED_API", "NPY_1_7_API_VERSION")]

# Optionally enable line tracing so coverage can collect ``.pyx`` line data
COVERAGE = os.environ.get("FIAT_CYTHON_COVERAGE", "").lower() in (
    "1",
    "on",
    "true",
    "yes",
)
if COVERAGE:
    directives_fiat["linetrace"] = True
    MACROS.append((("CYTHON_TRACE", "1")))


def _cpp_flags() -> list:
    """Return the C++17 selection flag for the active compiler."""
    if sys.platform == "win32":
        return ["/std:c++17", "/EHsc"]
    return ["-std=c++17"]


def _include_directories() -> list:
    """Return the environment include dir holding header files."""
    prefix = os.environ.get("CONDA_PREFIX") or os.environ.get("PREFIX") or sys.prefix
    candidates = [
        os.path.join(prefix, "Library", "include"),  # Windows (conda)
        os.path.join(prefix, "include"),  # Linux / macOS
    ]
    return [path for path in candidates if os.path.isdir(path)]


def _library_directories() -> list:
    """Return the environment lib dir holding shared libraries (e.g. zlib)."""
    prefix = os.environ.get("CONDA_PREFIX") or os.environ.get("PREFIX") or sys.prefix
    candidates = [
        os.path.join(prefix, "Library", "lib"),  # Windows (conda)
        os.path.join(prefix, "lib"),  # Linux / macOS
    ]
    return [path for path in candidates if os.path.isdir(path)]


def _zlib_linking() -> dict:
    """Link zlib statically when a static archive is available."""
    for lib_dir in _library_directories():
        for name in ("libz.a", "zlibstatic.lib"):
            candidate = os.path.join(lib_dir, name)
            if os.path.isfile(candidate):
                return {"extra_objects": [candidate]}
    return {"libraries": ["z"], "library_dirs": _library_directories()}


def _module_name(pyx_path: str) -> str:
    """Derive the dotted module name from a path under ``src``."""
    rel = os.path.relpath(pyx_path, "src")
    rel = os.path.splitext(rel)[0]
    return rel.replace(os.sep, ".")


def _fgb_ext() -> list:
    """Set the flatgeobuf extensions (bindings, reader, writer)."""
    global EXTENSIONS
    cpp_sources = [
        os.path.join(FGB_DIR, "fgb_c.cpp"),
        os.path.join(FGB_DIR, "packedrtree.cpp"),
    ]
    include_dirs = [numpy.get_include(), FGB_DIR, *_include_directories()]
    # Each compiled module and the extra C++ sources it needs to link.
    modules = {
        "reader": cpp_sources,
        "serialize": [],
        "writer": cpp_sources,
    }
    exts = []
    for stem, extra in modules.items():
        pyx = os.path.join(FGB_DIR, stem + ".pyx")
        EXTENSIONS.remove(pyx)
        exts.append(
            Extension(
                name=_module_name(os.path.normpath(pyx)),
                sources=[pyx, *extra],
                include_dirs=include_dirs,
                define_macros=MACROS,
                language="c++",
                extra_compile_args=_cpp_flags(),
            )
        )
    return exts


def _geotiff_ext() -> list:
    """Set the geotiff extensions (reader, writer)."""
    global EXTENSIONS
    cpp_sources = [os.path.join(GEOTIFF_DIR, "tiff_c.cpp")]
    include_dirs = [numpy.get_include(), GEOTIFF_DIR, *_include_directories()]
    zlib_link = _zlib_linking()
    exts = []
    for stem in ("reader", "writer"):
        pyx = os.path.join(GEOTIFF_DIR, stem + ".pyx")
        if pyx not in EXTENSIONS:
            continue
        EXTENSIONS.remove(pyx)
        exts.append(
            Extension(
                name=_module_name(os.path.normpath(pyx)),
                sources=[pyx, *cpp_sources],
                include_dirs=include_dirs,
                define_macros=MACROS,
                language="c++",
                extra_compile_args=_cpp_flags(),
                **zlib_link,
            )
        )
    return exts


def _pure_cython_ext() -> list:
    """Set all pure cython extensions, no dependency on a c/ c++ module."""
    exts = []
    for ext in EXTENSIONS:
        name = _module_name(os.path.normpath(ext))
        exts.append(
            Extension(
                name=name,
                sources=[ext],
                include_dirs=[numpy.get_include()],
                define_macros=MACROS,
            )
        )
    return exts


setup(
    ext_modules=cythonize(
        _fgb_ext() + _geotiff_ext() + _pure_cython_ext(),
        annotate=False,
        build_dir=build_dir,
        force=True,
        compiler_directives=directives_fiat,
        quiet=False,
    ),
    zip_safe=False,
)
