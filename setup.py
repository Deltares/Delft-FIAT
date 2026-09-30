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
    "nonecheck": False,
    "wraparound": False,
}

# Set some global variables
# Set all extensions
EXTENSIONS = glob.glob("src/fiat/**/*.pyx", recursive=True)
# The flatgeobuf source directory
FGB_DIR = os.path.join("src", "fiat", "driver", "_fgb")
# Set the numpy macros
NUMPY_MACROS = [("NPY_NO_DEPRECATED_API", "NPY_1_7_API_VERSION")]


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


def _module_name(pyx_path: str) -> str:
    """Derive the dotted module name from a path under ``src``."""
    rel = os.path.relpath(pyx_path, "src")
    rel = os.path.splitext(rel)[0]
    return rel.replace(os.sep, ".")


def _fgb_ext() -> list:
    """Set the flatgeobuf extension."""
    ext = os.path.join(FGB_DIR, "fgb.pyx")
    global EXTENSIONS
    EXTENSIONS.remove(ext)
    name = _module_name(os.path.normpath(ext))
    return [
        Extension(
            name=name,
            sources=[
                ext,
                os.path.join(FGB_DIR, "packedrtree.cpp"),
                os.path.join(FGB_DIR, "fgb_c.cpp"),
            ],
            include_dirs=[numpy.get_include(), FGB_DIR, *_include_directories()],
            define_macros=NUMPY_MACROS,
            language="c++",
            extra_compile_args=_cpp_flags(),
        )
    ]


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
                define_macros=NUMPY_MACROS,
            )
        )
    return exts


setup(
    ext_modules=cythonize(
        _fgb_ext() + _pure_cython_ext(),
        annotate=False,
        build_dir=build_dir,
        force=True,
        compiler_directives=directives_fiat,
        quiet=False,
    ),
    zip_safe=False,
)
