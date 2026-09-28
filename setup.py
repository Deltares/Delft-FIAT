"""Build script for FIAT's compiled (Cython) acceleration core.

Project metadata lives in ``pyproject.toml``; this file only declares the
mandatory Cython extension modules so that ``setuptools`` compiles them during
(editable) installs and wheel builds.
"""

import numpy as np
from Cython.Build import cythonize
from setuptools import Extension, setup

COMPILER_DIRECTIVES = {
    "language_level": "3",
    "boundscheck": False,
    "wraparound": False,
    "cdivision": True,
}

extensions = [
    Extension(
        "fiat._core._interp",
        ["src/fiat/_core/_interp.pyx"],
        include_dirs=[np.get_include()],
        define_macros=[("NPY_NO_DEPRECATED_API", "NPY_1_7_API_VERSION")],
    ),
    Extension(
        "fiat._core._overlay",
        ["src/fiat/_core/_overlay.pyx"],
        include_dirs=[np.get_include()],
        define_macros=[("NPY_NO_DEPRECATED_API", "NPY_1_7_API_VERSION")],
    ),
    Extension(
        "fiat._core._zonal",
        ["src/fiat/_core/_zonal.pyx"],
    ),
]

setup(
    ext_modules=cythonize(
        extensions,
        compiler_directives=COMPILER_DIRECTIVES,
    ),
)
