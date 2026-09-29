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

# Vendored FlatGeobuf / FlatBuffers C++ sources for the custom vector driver.
FGB_DIR = os.path.join("src", "fiat", "driver", "_fgb")
# The C++ Cython module(s) that bind the vendored FlatGeobuf sources.
CPP_MODULES = {
    os.path.normpath(os.path.join(FGB_DIR, "fgb.pyx")),
}

NUMPY_MACROS = [("NPY_NO_DEPRECATED_API", "NPY_1_7_API_VERSION")]


def _module_name(pyx_path: str) -> str:
    """Derive the dotted module name from a path under ``src``."""
    rel = os.path.relpath(pyx_path, "src")
    rel = os.path.splitext(rel)[0]
    return rel.replace(os.sep, ".")


def _cpp_std_args() -> list:
    """Return the C++17 selection flag for the active compiler."""
    if sys.platform == "win32":
        return ["/std:c++17", "/EHsc"]
    return ["-std=c++17"]


def _conda_include_dirs() -> list:
    """Return the conda environment include dir holding the FlatBuffers headers.

    FlatBuffers is a build-time (host) conda dependency; its C++ headers live under
    the environment prefix. ``CONDA_PREFIX`` is preferred so the correct env is used
    even under build isolation, falling back to ``PREFIX`` and ``sys.prefix``.
    """
    prefix = os.environ.get("CONDA_PREFIX") or os.environ.get("PREFIX") or sys.prefix
    candidates = [
        os.path.join(prefix, "Library", "include"),  # Windows (conda)
        os.path.join(prefix, "include"),  # Linux / macOS
    ]
    return [path for path in candidates if os.path.isdir(path)]


def _make_extensions() -> list:
    exts = []
    fb_include = _conda_include_dirs()
    for pyx in glob.glob("src/fiat/**/*.pyx", recursive=True):
        norm = os.path.normpath(pyx)
        name = _module_name(norm)
        if norm in CPP_MODULES:
            exts.append(
                Extension(
                    name=name,
                    sources=[
                        pyx,
                        os.path.join(FGB_DIR, "packedrtree.cpp"),
                        os.path.join(FGB_DIR, "fgb_c.cpp"),
                    ],
                    include_dirs=[numpy.get_include(), FGB_DIR, *fb_include],
                    define_macros=NUMPY_MACROS,
                    language="c++",
                    extra_compile_args=_cpp_std_args(),
                )
            )
        else:
            exts.append(
                Extension(
                    name=name,
                    sources=[pyx],
                    include_dirs=[numpy.get_include()],
                    define_macros=NUMPY_MACROS,
                )
            )
    return exts


setup(
    ext_modules=cythonize(
        _make_extensions(),
        annotate=False,
        build_dir=build_dir,
        force=True,
        compiler_directives=directives_fiat,
        quiet=False,
    ),
    zip_safe=False,
)
