# Vendored FlatGeobuf sources

These files are vendored (copied verbatim) third-party sources used to build FIAT's
custom Cython FlatGeobuf driver. They are **not** FIAT code and should not be edited by
hand.

## FlatGeobuf (BSD-2-Clause)
Source: https://github.com/flatgeobuf/flatgeobuf (`src/cpp`, `master`)

- `feature_generated.h` — flatc-generated from `src/fbs/feature.fbs`
- `header_generated.h` — flatc-generated from `src/fbs/header.fbs`
- `packedrtree.h`, `packedrtree.cpp` — packed Hilbert R-tree (index build + bbox query)

## FlatBuffers (build dependency, Apache-2.0)
The generated headers `#include "flatbuffers/flatbuffers.h"` and `static_assert` the
FlatBuffers runtime version **24.12.23**. FlatBuffers is **not vendored**; it is a
build-time conda dependency (`flatbuffers=24.12.23`, see `pyproject.toml`). Its C++
headers are provided by the environment and located at build time via
`setup.py:_conda_include_dirs()` (using `CONDA_PREFIX`/`PREFIX`/`sys.prefix`).

If FlatBuffers is bumped, the generated headers must be regenerated with the matching
`flatc` and the pinned `flatbuffers` dependency updated together.
