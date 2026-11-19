import pytest

from fiat._core import Interp1D
from fiat.driver import Table


@pytest.fixture(scope="session")
def vulnerability_fn1(vulnerability_data: Table) -> Interp1D:
    fn = Interp1D(
        vulnerability_data.index,
        vulnerability_data[:, "struct_1"],
    )
    return fn
