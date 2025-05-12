from pathlib import Path

import numpy as np
import pytest

from fiat.fio import (
    GeomIO,
    GridSource,
    open_csv,
    open_geom,
    open_grid,
)
from fiat.fio.handler import BufferHandler
from fiat.struct import Table, TableLazy


def test_open_csv_default(exposure_data_path: Path):
    # Open the dataset
    ds = open_csv(exposure_data_path)

    # Assert some simple stuff
    assert isinstance(ds, Table)
    assert isinstance(ds.data, np.ndarray)


def test_open_csv_delimiter(exposure_data_path: Path):
    # Open the dataset
    ds = open_csv(exposure_data_path)

    # Assert the shape
    assert ds.shape == (5, 6)  # 5 rows and 6 columns

    # Select another delimiter (wrong one)
    ds = open_csv(exposure_data_path, delimiter=";")

    # Assert the shape
    assert ds.shape == (5, 1)  # No more columns as they can't be separated


def test_open_csv_header(exposure_data_path: Path):
    # Open the dataset
    ds = open_csv(exposure_data_path, header=True)  # Which is default

    # Assert the columns
    assert ds.columns == (
        "object_id",
        "extract_method",
        "ground_flht",
        "ground_elevtn",
        "fn_damage_structure",
        "max_damage_structure",
    )  # Very specific, but this should be True for this dataset

    # No header
    ds = open_csv(exposure_data_path, header=False)

    # Assert the default columns
    assert ds.columns == ("col_0", "col_1", "col_2", "col_3", "col_4", "col_5")


def test_open_csv_index(exposure_data_path: Path):
    # Open the dataset
    ds = open_csv(exposure_data_path, index=None)  # Which is default

    # Assert the index and name
    assert ds.index_name == "index"
    assert ds.index == (0, 1, 2, 3, 4)  # Default

    # Open with selected header
    ds = open_csv(exposure_data_path, index="object_id")

    # Assert the new index
    assert ds.index_name == "object_id"
    assert ds.index == (1, 2, 3, 4, 5)


def test_open_csv_lazy(exposure_data_path: Path):
    # Open the dataset in lazy mode
    ds = open_csv(exposure_data_path, lazy=True)

    # Assert some simple stuff
    assert isinstance(ds, TableLazy)
    assert isinstance(ds.data, BufferHandler)  # A stream handler is the data


def test_open_geom_context(exposure_geom_path: Path):
    # Open the dataset with context manager
    with open_geom(exposure_geom_path) as reader:
        # Assert some simple stuff
        assert isinstance(reader, GeomIO)
        assert reader.mode == 0  # Read only
        assert reader.layer is not None

    # Now it's closed but not deleted
    assert reader.closed == True
    assert reader.src is None

    with pytest.raises(
        ValueError,
        match="Invalid operation on a closed file",
    ):
        # Get the layer
        _ = reader.layer


def test_open_geom_read_only(exposure_geom_path: Path):
    # Open the dataset
    ds = open_geom(exposure_geom_path)

    # Assert simple stufValueErrorf
    assert isinstance(ds, GeomIO)
    assert ds.mode == 0  # Read only
    assert ds.layer is not None

    ds.close()


def test_open_geom_write_new(tmp_path: Path):
    # Open a dataset in write mode
    ds = open_geom(Path(tmp_path, "tmp.geojson"), mode="w")

    # Assert some simple stuff
    assert isinstance(ds, GeomIO)
    assert ds.mode == 1  # Write/ update mode
    assert ds.layer is None  # Hasn't been created yet

    ds.close()


def test_open_geom_write_append(exposure_geom_tmp_path: Path):
    # Open a dataset in write mode
    ds = open_geom(exposure_geom_tmp_path, mode="w")

    # Assert some simple stuff
    assert isinstance(ds, GeomIO)
    assert ds.mode == 1  # Write/ update mode
    assert ds.layer is not None  # Hasn't been created yet
    assert ds.layer.size == 4

    ds.close()


def test_open_geom_write_overwrite(exposure_geom_tmp_path: Path):
    # Open a dataset in write mode
    ds = open_geom(exposure_geom_tmp_path, mode="w", overwrite=True)

    # Assert some simple stuff
    assert isinstance(ds, GeomIO)
    assert ds.mode == 1  # Write/ update mode
    assert ds.layer is None  # Overwritten source, so has to be newly created

    ds.close()


def test_open_grid_context(hazard_event_path: Path):
    # Open the dataset with context managesubsetr
    with open_grid(hazard_event_path) as reader:
        # Assert some simple stuff
        assert isinstance(reader, GridSource)
        assert reader.size == 1  # One band

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
    assert isinstance(ds, GridSource)
    assert ds.size == 1  # One band

    ds.close()


def test_open_grid_chunk(hazard_event_path: Path):
    # Open the dataset
    ds = open_grid(hazard_event_path, chunk=None)  # Default

    # Assert some simple stuff
    assert ds.shape == (10, 10)
    assert ds.chunk == (10, 10)  # As no chunking was given, it is set to the shape

    ds.close()

    # Open the dataset with chunks
    ds = open_grid(hazard_event_path, chunk=(4, 4))

    # Assert some simple stuff
    assert ds.shape == (10, 10)
    assert ds.chunk == (4, 4)

    ds.close()


def test_open_grid_subset(hazard_risk_path: Path):
    # Open the dataset
    ds = open_grid(hazard_risk_path, subset=None)  # Default

    # Assert some simple stuff
    assert ds.size == 0  # Nothing found
    assert ds.subset_dict is not None  # Subsets are found

    ds.close()

    # Open the dataset, but ask for as subset (band)
    ds = open_grid(hazard_risk_path, subset="Band1")

    # Assert some simple stuff
    assert ds.size == 1  # A single band
    assert ds.subset_dict is None  # No longer any subsets

    ds.close()


def test_open_grid_var(hazard_risk_path: Path):
    # Open the dataset
    ds = open_grid(hazard_risk_path, var_as_band=False)  # Default

    # Assert some simple stuff
    assert ds.size == 0  # Nothing found
    assert ds.subset_dict is not None  # Subsets are found

    ds.close()

    # Open the dataset, but handle the subsets as bands
    ds = open_grid(hazard_risk_path, var_as_band=True)

    # Assert some simple stuff
    assert ds.size == 4  # All subsets as bands
    assert ds.subset_dict is None  # No longer any subsets

    ds.close()


def test_open_grid_write(tmp_path: Path):
    p = Path(tmp_path, "tmp.nc")
    # Open a dataset
    ds = open_grid(p, mode="w")

    # Assert some simple stuff
    assert ds.mode == 1
    assert ds.src is None
