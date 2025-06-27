import io
import re
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock

import pytest
from osgeo import osr

from fiat import Configurations
from fiat.check import (
    check_config_entries,
    check_config_grid,
    check_duplicate_columns,
    check_exp_columns,
    check_exp_derived_types,
    check_exp_grid_dmfs,
    check_exp_index_col,
    check_geom_extent,
    check_grid_exact,
    check_hazard_band_names,
    check_hazard_rp,
    check_hazard_subsets,
    check_internal_srs,
    check_vs_srs,
)
from fiat.error import FIATDataError
from fiat.log import Logger
from fiat.methods.flood import MANDATORY_COLUMNS
from fiat.util import MANDATORY_MODEL_ENTRIES


def test_check_config_entries_fail():
    # Call the function with entries missing
    with pytest.raises(
        FIATDataError,
        match=re.escape(
            "Data error -> Missing mandatory entries in the settings. \
Please fill in the following missing entries: ['vulnerability.file']"
        ),
    ):
        check_config_entries(
            ("hazard.file",),
            MANDATORY_MODEL_ENTRIES,
        )


def test_check_config_entries_pass():
    # Call the function with all entries present
    check_config_entries(
        ("hazard.file", "vulnerability.file"),
        MANDATORY_MODEL_ENTRIES,
    )


def test_check_config_grid_fail(config: Configurations):
    # Call the function with missing entry
    b = check_config_grid(config)
    # Assert it's not there, therefore false
    assert not b

    # Call the function with missing entry but with grid stuff
    config.set("exposure.grid.settings.srs", "EPSG:4326")
    b = check_config_grid(config)
    # Assert it's not there, therefore false
    assert not b


def test_check_config_grid_pass(config: Configurations):
    # Adjust to config to add the exposure grid file
    config.set("exposure.grid.file", "foo.txt")
    # Call the function with missing entry
    b = check_config_grid(config)
    # Assert it's not there, therefore false
    assert b


def test_check_duplicate_columns_fail():
    # Call the function with not None input
    with pytest.raises(
        FIATDataError,
        match=re.escape(
            "Duplicate columns were encountered. Wrong column could \
be used. Check input for these columns: ['foo', 'bar']"
        ),
    ):
        check_duplicate_columns(["foo", "bar"])


def test_check_duplicate_columns_pass():
    # Call the function with None input
    check_duplicate_columns(None)  # Should pass


def test_check_exp_columns_fail():
    # Call the function with missing Mandatory column
    with pytest.raises(
        FIATDataError,
        match=re.escape("Missing mandatory exposure columns: ['ground_flht']"),
    ):
        check_exp_columns(
            ["object_id", "ground_elevtn"],
            index_col="object_id",
            mandatory_columns=MANDATORY_COLUMNS,
        )

    # Call the function with missing index column
    with pytest.raises(
        FIATDataError,
        match=re.escape("Missing mandatory exposure columns: ['object_id']"),
    ):
        check_exp_columns(
            ["ground_elevtn", "ground_flht"],
            index_col="object_id",
            mandatory_columns=MANDATORY_COLUMNS,
        )


def test_check_exp_columns_pass():
    # Call the function with all columns there
    check_exp_columns(
        ["object_id", "ground_elevtn", "ground_flht"],
        index_col="object_id",
        mandatory_columns=MANDATORY_COLUMNS,
    )


def test_check_exp_derived_types_fail():
    # No columns found for a certain exposure type
    with pytest.raises(
        FIATDataError,
        match=re.escape(
            "For type: 'damage' no matching columns were found for \
fn_damage_* and max_damage_* columns."
        ),
    ):
        check_exp_derived_types(
            type="damage",
            found=[],
            missing=[],  # Doesnt matter here
        )


def test_check_exp_derived_types_pass(
    log_capture: io.StringIO,
    logger_stream: Logger,
):
    # Columns found
    check_exp_derived_types(
        type="damage",
        found=["structure"],
        missing=[],  # Doesnt matter here
    )

    # Missing either fn or max for a certain subtype results in a warning
    check_exp_derived_types(
        type="damage",
        found=["structure"],
        missing=["content"],  # Doesnt matter here
    )

    # Assert the logging message
    log_capture.seek(0)
    cap = log_capture.read()
    assert (
        "No every damage function has a corresponding \
maximum potential damage: ['content']"
        in cap
    )


def test_check_exp_grid_dmfs_fail():
    # Call the function with an unknown damage function
    with pytest.raises(
        FIATDataError,
        match=re.escape(
            "Unknown damage function identifier found in \
exposure grid: ['bar']"
        ),
    ):
        check_exp_grid_dmfs(
            fns=["foo", "bar"],
            dmfs=["foo", "baz"],
        )


def test_check_exp_grid_dmfs_pass():
    # Call the function with all functions known
    check_exp_grid_dmfs(
        fns=["foo", "bar"],
        dmfs=["foo", "bar", "baz"],
    )


def test_check_exp_index_col_fail():
    # Call the function with the index_col not present
    with pytest.raises(
        FIATDataError,
        match=re.escape("Index column ('foo') not found in baz"),
    ):
        check_exp_index_col(
            columns=["bar", "spooky"],
            index_col="foo",
            path="baz",
        )


def test_check_exp_index_col_pass():
    # Call the function with the index_col not present
    check_exp_index_col(
        columns=["foo", "bar", "spooky"],
        index_col="foo",
        path="baz",
    )


def test_check_geom_extent_fail(
    log_capture: io.StringIO,
    logger_stream: Logger,
):
    # Bounds exceed
    check_geom_extent(
        gm_bounds=[0, 1, 0, 1],
        gr_bounds=[0, 1, 0, 0.5],
    )

    # Assert the logging message
    log_capture.seek(0)
    cap = log_capture.read()
    assert (
        "Geometry bounds [0, 1, 0, 1] exceed \
hazard bounds [0, 1, 0, 0.5]"
        in cap
    )


def test_check_geom_extent_pass(
    log_capture: io.StringIO,
    logger_stream: Logger,
):
    # Bounds is within
    check_geom_extent(
        gm_bounds=[0, 1, 0, 1],
        gr_bounds=[0, 1, 0, 1],
    )

    # Assert no logging message
    log_capture.seek(0)
    cap = log_capture.read()
    assert cap == ""


def test_check_grid_exact_fail_srs(
    mocked_hazard_grid: MagicMock,
    mocked_exp_grid: MagicMock,
    log_capture: io.StringIO,
    logger_stream: Logger,
):
    # Set a different srs
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(3857)
    type(mocked_exp_grid).srs = PropertyMock(side_effect=lambda: srs)

    # Call the method should produce a warning and a False return
    b = check_grid_exact(mocked_hazard_grid, mocked_exp_grid)

    # Assert the output
    assert not b
    log_capture.seek(0)
    cap = log_capture.read()
    assert (
        "CRS of hazard data (EPSG:4326) does not match the \
CRS of the exposure data (EPSG:3857)"
        in cap
    )


def test_check_grid_exact_fail_gtf(
    mocked_hazard_grid: MagicMock,
    mocked_exp_grid: MagicMock,
    log_capture: io.StringIO,
    logger_stream: Logger,
):
    # Set a different geo transform
    type(mocked_exp_grid).geotransform = PropertyMock(
        side_effect=lambda: (0, 0.5, 0, 10, 0, -0.5),
    )

    # Call the method should produce a warning and a False return
    b = check_grid_exact(mocked_hazard_grid, mocked_exp_grid)

    # Assert the output
    assert not b
    log_capture.seek(0)
    cap = log_capture.read()
    assert (
        "Geotransform of hazard data ([0, 1.0, 0.0, 10.0, 0.0, -1.0]) does not \
match geotransform of exposure data ([0, 0.5, 0, 10, 0, -0.5])"
        in cap
    )


def test_check_grid_exact_fail_shape(
    mocked_hazard_grid: MagicMock,
    mocked_exp_grid: MagicMock,
    log_capture: io.StringIO,
    logger_stream: Logger,
):
    # Set a different shape
    type(mocked_exp_grid).shape = PropertyMock(side_effect=lambda: (5, 5))

    # Call the method should produce a warning and a False return
    b = check_grid_exact(mocked_hazard_grid, mocked_exp_grid)

    # Assert the output
    assert not b
    log_capture.seek(0)
    cap = log_capture.read()
    assert (
        "Shape of hazard ((10, 10)) does not match shape of \
exposure data ((5, 5))"
        in cap
    )


def test_check_grid_exact_pass(
    mocked_hazard_grid: MagicMock,
    mocked_exp_grid: MagicMock,
    log_capture: io.StringIO,
    logger_stream: Logger,
):
    # Call the method which should return true and no logging message
    b = check_grid_exact(mocked_hazard_grid, mocked_exp_grid)

    # Assert the output
    assert b
    log_capture.seek(0)
    cap = log_capture.read()
    assert cap == ""


def test_check_hazard_band_names():
    # Call the function
    b = check_hazard_band_names(["foo", "bar"], risk=False, rp=None, count=2)
    # Assert the output
    assert b == ["foo", "bar"]

    # Count is one
    b = check_hazard_band_names(["foo", "bar"], risk=False, rp=None, count=1)
    # Assert the output
    assert b == [""]


def test_check_hazard_band_names_risk():
    # Call the function
    b = check_hazard_band_names(["foo", "bar"], risk=True, rp=[1, 2], count=2)
    # Assert the output
    assert b == ["1y", "2y"]


def test_check_hazard_rp_fail():
    # Call the function with a missing rp value compared to the bands
    with pytest.raises(
        FIATDataError,
        match="'tmp.txt': cannot determine the return periods \
for the risk calculation",
    ):
        check_hazard_rp(
            rp_bands=["a", "b", "c", "d"],
            rp_cfg=[1.0, 2.0, 5.0],
            path=Path("tmp.txt"),
        )


def test_check_hazard_rp_pass():
    # Call the function with everything present and matching
    rp = check_hazard_rp(
        rp_bands=["a", "b", "c", "d"],
        rp_cfg=[1.0, 2.0, 5.0, 10.0],
        path=Path("tmp.txt"),
    )

    # Assert the output
    rp == [1.0, 2.0, 5.0, 10.0]


def test_check_hazard_subsets_fail():
    # Call the function with subsets present, i.e. netcdf
    with pytest.raises(
        FIATDataError,
        match=re.escape(
            "'tmp.nc': cannot read this file as there are multiple \
datasets (subsets). Chose one of the following subsets: foo, bar"
        ),
    ):
        check_hazard_subsets(
            sub={"foo": None, "bar": None},
            path=Path("tmp.nc"),
        )


def test_check_hazard_subsets_pass():
    # Call the function with no sub datasets
    check_hazard_subsets(
        sub=None,
        path=Path("tmp.nc"),
    )


def test_check_internal_srs_fail():
    # Call the function with no known srs
    with pytest.raises(
        FIATDataError,
        match=re.escape(
            "Coordinate reference system is unknown for 'tmp.nc', \
cannot safely continu"
        ),
    ):
        check_internal_srs(
            source_srs=None,
            fname="tmp.nc",
        )


def test_check_internal_srs_pass():
    # Call the function with a srs
    check_internal_srs(
        source_srs="EPSG:4326",
        fname="tmp.nc",
    )


def test_check_vs_srs_fail(srs: osr.SpatialReference):
    # Setup up another srs
    other = osr.SpatialReference()
    other.ImportFromEPSG(3857)
    # Call the function with the different srs
    b = check_vs_srs(srs, other)

    # Assert the output
    assert not b


def test_check_vs_srs_pass(srs: osr.SpatialReference):
    # Call the function with the different srs
    b = check_vs_srs(srs, srs)

    # Assert the output
    assert b
