"""Setup for cython extensions."""

import os

import numpy
from Cython.Build import cythonize
from Cython.Compiler import Options
from setuptools import Extension, setup

build_dir = "build"
os.makedirs(build_dir, exist_ok=True)
Options.annotate = True

extensions = [
    Extension(
        name="*",
        sources=["src/fiat/**/*.pyx"],
        include_dirs=[numpy.get_include()],
        define_macros=[("NPY_NO_DEPRECATED_API", "NPY_1_7_API_VERSION")],
    )
]

setup(
    ext_modules=cythonize(
        extensions,
        annotate=False,
        build_dir=build_dir,
        force=True,
        compiler_directives={"language_level": "3", "profile": False},
        quiet=True,
    ),
    zip_safe=False,
)
