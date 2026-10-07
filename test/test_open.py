from pathlib import Path

import numpy as np
import pytest

from fiat.driver import (
    FlatGeobufReader,
    NetcdfReader,
)
from fiat.driver.csv import Table
from fiat.error import DriverNotFoundError
from fiat.open import open_csv, open_geom, open_grid


def test_open_csv_default(vulnerability_path: Path):
    # Open the dataset
    ds = open_csv(vulnerability_path)

    # Assert some simple stuff
    assert isinstance(ds, Table)
    assert isinstance(ds.data, np.ndarray)


def test_open_csv_delimiter(vulnerability_path: Path):
    # Open the dataset
    ds = open_csv(vulnerability_path)

    # Assert the shape
    assert ds.shape == (21, 3)  # 5 rows and 6 columns

    # Select another delimiter (wrong one)
    ds = open_csv(vulnerability_path, delimiter=";")

    # Assert the shape
    assert ds.shape == (21, 1)  # No more columns as they can't be separated


def test_open_csv_header(vulnerability_path: Path):
    # Open the dataset
    ds = open_csv(vulnerability_path, header=True)  # Which is default

    # Assert the columns
    assert ds.columns == (
        "depth",
        "struct_1",
        "struct_2",
    )  # Very specific, but this should be True for this dataset

    # No header
    ds = open_csv(vulnerability_path, header=False)

    # Assert the default columns
    assert ds.columns == ("col_0", "col_1", "col_2")


def test_open_csv_index(vulnerability_path: Path):
    # Open the dataset
    ds = open_csv(vulnerability_path, index=None)  # Which is default

    # Assert the index and name
    assert ds.index_name == "index"
    assert ds.index[:5] == (0, 1, 2, 3, 4)  # Default

    # Open with selected header
    ds = open_csv(vulnerability_path, index="depth")

    # Assert the new index
    assert ds.index_name == "depth"
    assert ds.index[:5] == (0.0, 0.25, 0.5, 0.75, 1.0)


def test_open_geom_context(exposure_geom_path: Path):
    # Open the dataset with context manager
    with open_geom(exposure_geom_path) as reader:
        # Assert some simple stuff
        assert isinstance(reader, FlatGeobufReader)
        assert reader.closed is False
        assert reader.profile.size == 4

    # Now it's closed
    assert reader.closed is True


def test_open_geom_read_only(exposure_geom_path: Path):
    # Open the dataset
    ds = open_geom(exposure_geom_path)

    # Assert simple stuff
    assert isinstance(ds, FlatGeobufReader)
    assert ds.profile.size == 4

    ds.close()


def test_open_geom_append(exposure_geom_tmp_path: Path):
    # Append mode still returns a reader over the existing source
    ds = open_geom(exposure_geom_tmp_path, mode="a")

    # Assert some simple stuff
    assert isinstance(ds, FlatGeobufReader)
    assert ds.profile.size == 4

    ds.close()


def test_open_geom_missing_file(tmp_path: Path):
    # A missing file raises a FileNotFoundError
    p = Path(tmp_path, "tmp.fgb")
    with pytest.raises(FileNotFoundError):
        _ = open_geom(p)


def test_open_geom_bad_extension(tmp_path: Path):
    # An unsupported extension raises a DriverNotFoundError
    with pytest.raises(
        DriverNotFoundError,
        match="Geometry data -> \
Extension of file: tmp.unknown not recoqnized",
    ):
        _ = open_geom(Path(tmp_path, "tmp.unknown"))


def test_open_grid_context(hazard_event_path: Path):
    # Open the dataset with context managesubsetr
    with open_grid(hazard_event_path) as reader:
        # Assert some simple stuff
        assert isinstance(reader, NetcdfReader)
        assert reader.size == 1  # One variable

    # Now it's closed but not deleted
    assert reader.closed == True
    assert reader.src is None

    with pytest.raises(
        ValueError,
        match="Invalid operation on a closed file",
    ):
        # Requent the size
        _ = reader.size


def test_open_grid_read_only(hazard_event_path: Path):
    # Open the dataset
    ds = open_grid(hazard_event_path)

    # Assert some simple stuff
    assert isinstance(ds, NetcdfReader)
    assert ds.size == 1  # One band

    ds.close()


def test_open_grid_append(hazard_event_tmp_path: Path):
    # Append mode still returns a reader over the existing source
    ds = open_grid(hazard_event_tmp_path, mode="a")

    # Assert some simple stuff
    assert isinstance(ds, NetcdfReader)
    assert ds.src is not None
    assert ds.size == 1

    ds.close()


def test_open_grid_write(tmp_path: Path):
    p = Path(tmp_path, "tmp.nc")
    # Open a dataset
    ds = open_grid(p, mode="w")

    # Assert some simple stuff
    assert ds.closed is False
    assert ds.src is not None
