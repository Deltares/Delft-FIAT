import netCDF4 as nc4
import numpy as np
import pytest

from fiat.driver import ConstantVariable, NetcdfReader
from fiat.error import FIATDataError
from fiat.model.util import (
    apply_constants,
    create_1d_chunks,
    create_2d_chunks,
    create_2d_windows,
)
from fiat.settings.hazard import HazardVariable
from fiat.settings.vulnerability import VulnerabilityVariable


def test_create_1d_chunks_few():
    # Call the function
    chunks = list(create_1d_chunks(500, 6))

    # Assert the output
    assert len(chunks) == 6
    assert chunks[0] == (1, 84)
    assert chunks[-1] == (421, 500)


def test_create_1d_chunks_many():
    # Call the function
    chunks = list(create_1d_chunks(500, 20))

    # Assert the output
    assert len(chunks) == 20
    assert chunks[0] == (1, 25)
    assert chunks[-1] == (476, 500)


def test_create_2d_chunks_few():
    # Call the function
    chunks = list(create_2d_chunks((500, 350), 2))

    # Assert the output
    assert len(chunks) == 2
    assert chunks[0] == (0, 0, 250, 350)
    assert chunks[1] == (250, 0, 250, 350)


def test_create_2d_chunks_many():
    # Call the function
    chunks = list(create_2d_chunks((500, 350), 10))

    # Assert the output
    assert len(chunks) == 10
    assert chunks[4] == (167, 105, 167, 105)
    assert chunks[7] == (125, 210, 125, 140)


def test_create_2d_windows_even():
    # Call the function
    windows = list(create_2d_windows((10, 10), (0, 0), (2, 2)))

    # Assert the output
    assert len(windows) == 25
    assert windows[0] == (slice(0, 2), slice(0, 2))
    assert windows[-1] == (slice(8, 10), slice(8, 10))  # Should nicely fit


def test_create_2d_windows_uneven():
    # Call the function
    windows = list(create_2d_windows((10, 10), (0, 0), (4, 4)))
    assert len(windows) == 9
    assert windows[0] == (slice(0, 4), slice(0, 4))
    assert windows[-1] == (slice(8, 10), slice(8, 10))
    # It's the same as it does not fit


def test_apply_constants_adds_layer(hazard_event_path):
    # Call the function with a listed file variable and a constant layer
    reader = NetcdfReader(hazard_event_path)
    apply_constants(
        reader,
        [
            HazardVariable(name="data", type="water_depth"),
            HazardVariable(name="dur", type="duration", value=3.0),
        ],
    )

    # Assert the constant layer, last in the reader
    assert reader.names == ["data", "dur"]
    var = reader.variables["dur"]
    assert isinstance(var, ConstantVariable)
    np.testing.assert_array_equal(var.load(), np.full((10, 10), 3.0))
    reader.close()


def test_apply_constants_ignores_unlisted(hazard_event_path):
    # Listing none of the file variables is fine, they are ignored
    reader = NetcdfReader(hazard_event_path)
    apply_constants(reader, [HazardVariable(name="dur", type="duration", value=3.0)])

    # Assert the file variable is still there
    assert reader.names == ["data", "dur"]
    reader.close()


def test_apply_constants_twice(hazard_event_path):
    # Applying the same constants again does not fail or duplicate
    reader = NetcdfReader(hazard_event_path)
    variables = [HazardVariable(name="dur", type="duration", value=3.0)]
    apply_constants(reader, variables)
    apply_constants(reader, variables)

    # Assert the output
    assert reader.names == ["data", "dur"]
    reader.close()


def test_apply_constants_missing(hazard_event_path):
    # A listed variable without a value that is not in the file
    reader = NetcdfReader(hazard_event_path)
    with pytest.raises(FIATDataError, match="not found"):
        apply_constants(reader, [HazardVariable(name="foo", type="water_depth")])


def test_apply_constants_value_existing(hazard_event_path):
    # A listed variable with a value that is in the file
    reader = NetcdfReader(hazard_event_path)
    with pytest.raises(FIATDataError, match="can't define it by a value"):
        apply_constants(
            reader,
            [HazardVariable(name="data", type="water_depth", value=1.0)],
        )


def test_apply_constants_no_spatial(vulnerability_path):
    # A constant layer on a dataset without spatial dimensions
    reader = NetcdfReader(vulnerability_path)
    with pytest.raises(FIATDataError, match="no spatial dimensions"):
        apply_constants(
            reader,
            [HazardVariable(name="dur", type="duration", value=3.0)],
        )


def test_apply_constants_vulnerability(vulnerability_path):
    # The variables without a value are only checked for existence
    reader = NetcdfReader(vulnerability_path)
    apply_constants(
        reader,
        [
            VulnerabilityVariable(
                name="default",
                method="flood.depth",
                types={"depth_default": "water_depth"},
            )
        ],
    )
    assert reader.names == ["default"]
    reader.close()


def test_apply_constants_error_closes_reader(
    monkeypatch: pytest.MonkeyPatch,
    hazard_event_path,
):
    # Keep track of the opened netcdf dataset
    opened = []
    dataset = nc4.Dataset

    def _dataset(*args, **kwargs):
        opened.append(dataset(*args, **kwargs))
        return opened[-1]

    monkeypatch.setattr(nc4, "Dataset", _dataset)
    reader = NetcdfReader(hazard_event_path)

    # A failing check closes the reader before raising
    with pytest.raises(FIATDataError, match="not found"):
        apply_constants(reader, [HazardVariable(name="foo", type="water_depth")])
    assert len(opened) == 1
    assert reader.closed
    assert not opened[0].isopen()
