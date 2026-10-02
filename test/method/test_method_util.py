import numpy as np

from fiat._core import zonal_reduce
from fiat.method.util import ZONAL_CODES, ZONAL_METHODS
from fiat.util import mean


def test_zonal_methods():
    # The method map holds the three reducers
    assert set(ZONAL_METHODS) == {"max", "mean", "min"}
    assert ZONAL_METHODS["max"] is max
    assert ZONAL_METHODS["mean"] is mean
    assert ZONAL_METHODS["min"] is min


def test_zonal_codes():
    data = np.ascontiguousarray([1.0, 2.0, 4.0], dtype=np.float64)

    # The codes line up with the compiled zonal_reduce
    assert ZONAL_CODES == {"mean": 0, "max": 1, "min": 2}
    assert zonal_reduce(data, ZONAL_CODES["mean"], 0.0) == (7.0 / 3.0, 1.0)
    assert zonal_reduce(data, ZONAL_CODES["max"], 0.0) == (4.0, 1.0)
    assert zonal_reduce(data, ZONAL_CODES["min"], 0.0) == (1.0, 1.0)
