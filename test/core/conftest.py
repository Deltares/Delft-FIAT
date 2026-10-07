import numpy as np
import pytest


## Footprint geometry (FlatGeobuf layout: interleaved xy + per-ring ends)
@pytest.fixture(scope="session")
def footprint_xy() -> np.ndarray:
    # POLYGON ((0.2 -0.2, 2.8 -0.2, 2.8 -2.8, 0.2 -2.8, 0.2 -0.2))
    xy = [0.2, -0.2, 2.8, -0.2, 2.8, -2.8, 0.2, -2.8, 0.2, -0.2]
    return np.ascontiguousarray(xy, dtype=np.float64)


@pytest.fixture(scope="session")
def footprint_ends() -> np.ndarray:
    ends = np.array([5], dtype=np.uint32)
    return ends
