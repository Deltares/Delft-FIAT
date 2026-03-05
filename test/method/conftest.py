from typing import Callable

import pytest
from scipy.interpolate import make_interp_spline

from fiat.struct import Table


@pytest.fixture(scope="session")
def vulnerability_fn1(vulnerability_data: Table) -> Callable:
    fn = make_interp_spline(
        vulnerability_data.index,
        vulnerability_data[:, "struct_1"],
    )
    return fn
