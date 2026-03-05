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
    check_exp_grid_fn,
    check_geom_extent,
    check_grid_exact,
    check_hazard_identifier,
    check_hazard_rp,
    check_hazard_subsets,
    check_hazard_types,
    check_input_data,
    check_internal_srs,
    check_vs_srs,
)
from fiat.error import FIATDataError
from fiat.log import Logger
from fiat.method.flood import COLUMNS
from fiat.struct import Container
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
            Configurations(**{"hazard": {"file": "foo"}}),
            MANDATORY_MODEL_ENTRIES,
        )


def test_check_config_entries_pass():
    # Call the function with all entries present
    check_config_entries(
        Configurations(**{"hazard": {"file": "foo"}, "vulnerability": {"file": "bar"}}),
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
        match=re.escape("Missing mandatory exposure columns: ['ref']"),
    ):
        check_exp_columns(
            ["object_id"],
            mandatory_columns=COLUMNS,
        )


def test_check_exp_columns_pass():
    # Call the function with all columns there
    check_exp_columns(
        ["object_id", "ref"],
        mandatory_columns=COLUMNS,
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
    caplog: Logger,
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
    assert (
        "No every damage function has a corresponding \
maximum potential damage: ['content']"
        in caplog.text
    )


def test_check_exp_grid_fn_fail():
    # Call the function with an unknown damage function
    with pytest.raises(
        FIATDataError,
        match=re.escape(
            "Unknown impact function identifier found in \
exposure grid: ['bar']"
        ),
    ):
        check_exp_grid_fn(
            fn_list=["foo", "bar"],
            fn_available=["foo", "baz"],
        )


def test_check_exp_grid_fn_pass():
    # Call the function with all functions known
    check_exp_grid_fn(
        fn_list=["foo", "bar"],
        fn_available=["foo", "bar", "baz"],
    )


def test_check_geom_extent_fail(
    caplog: Logger,
):
    # Bounds exceed
    check_geom_extent(
        gm_bounds=[0, 0, 1, 1],
        gr_bounds=[0, 0, 1, 0.5],
    )

    # Assert the logging message
    assert (
        "Geometry bounds [0, 0, 1, 1] exceed \
hazard bounds [0, 0, 1, 0.5]"
        in caplog.text
    )


def test_check_geom_extent_pass(
    caplog: Logger,
):
    # Bounds is within
    check_geom_extent(
        gm_bounds=[0, 0, 1, 1],
        gr_bounds=[0, 0, 1, 1],
    )

    # Assert no logging message
    assert caplog.text == ""


def test_check_grid_exact_fail_srs(
    mocked_hazard_grid: MagicMock,
    mocked_exp_grid: MagicMock,
    caplog: Logger,
):
    # Set a different srs
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(3857)
    type(mocked_exp_grid).srs = PropertyMock(side_effect=lambda: srs)

    # Call the method should produce a warning and a False return
    b = check_grid_exact(mocked_hazard_grid, mocked_exp_grid)

    # Assert the output
    assert not b
    assert (
        "CRS of hazard data (EPSG:4326) does not match the \
CRS of the exposure data (EPSG:3857)"
        in caplog.text
    )


def test_check_grid_exact_fail_gtf(
    mocked_hazard_grid: MagicMock,
    mocked_exp_grid: MagicMock,
    caplog: Logger,
):
    # Set a different geo transform
    type(mocked_exp_grid).geotransform = PropertyMock(
        side_effect=lambda: (0, 0.5, 0, 10, 0, -0.5),
    )

    # Call the method should produce a warning and a False return
    b = check_grid_exact(mocked_hazard_grid, mocked_exp_grid)

    # Assert the output
    assert not b
    assert (
        "Geotransform of hazard data ([0, 1.0, 0.0, 10.0, 0.0, -1.0]) does not \
match geotransform of exposure data ([0, 0.5, 0, 10, 0, -0.5])"
        in caplog.text
    )


def test_check_grid_exact_fail_shape(
    mocked_hazard_grid: MagicMock,
    mocked_exp_grid: MagicMock,
    caplog: Logger,
):
    # Set a different shape
    type(mocked_exp_grid).shape = PropertyMock(side_effect=lambda: (5, 5))

    # Call the method should produce a warning and a False return
    b = check_grid_exact(mocked_hazard_grid, mocked_exp_grid)

    # Assert the output
    assert not b
    assert (
        "Shape of hazard ((10, 10)) does not match shape of \
exposure data ((5, 5))"
        in caplog.text
    )


def test_check_grid_exact_pass(
    mocked_hazard_grid: MagicMock,
    mocked_exp_grid: MagicMock,
    caplog: Logger,
):
    # Call the method which should return true and no logging message
    b = check_grid_exact(mocked_hazard_grid, mocked_exp_grid)

    # Assert the output
    assert b
    assert caplog.text == ""


def test_check_hazard_identifier_fail():
    # Call the function with a duplicate identifier
    with pytest.raises(
        FIATDataError,
        match="Data error -> Identifiers set incorrectly for type",
    ):
        check_hazard_identifier(
            ids=["a", "b", "b", "d"],
            indices_type=[[0, 1, 2, 3]],
        )


def test_check_hazard_identifier_pass():
    # Call the function with everything present and matching
    out, _ = check_hazard_identifier(
        ids=["1", "2", "5", "10"],
        indices_type=[[0, 1, 2, 3]],
    )

    # Assert the output
    assert out == ["1", "2", "5", "10"]


def test_check_hazard_identifier_multi_fail():
    # Call the function with an extra identifier
    with pytest.raises(
        FIATDataError,
        match="Data error -> Identifiers across types do not match total:",
    ):
        check_hazard_identifier(
            ids=["a", "b", "c", "d", "a", "b", "c", "e"],
            indices_type=[[0, 1, 2, 3], [4, 5, 6, 7]],
        )


def test_check_hazard_identifier_multi_pass():
    # Call the function with everything present and matching
    out, _ = check_hazard_identifier(
        ids=["a", "b", "c", "d", "b", "a", "d", "c"],
        indices_type=[[0, 1, 2, 3], [4, 5, 6, 7]],
    )

    # Assert the output
    assert out == ["a", "b", "c", "d"]


def test_check_hazard_rp_fail():
    # Call the function with a string in there (really a string)
    with pytest.raises(
        FIATDataError, match="Data error -> Wrong type in return periods:"
    ):
        _ = check_hazard_rp(["2", "5", "foo"])


def test_check_hazard_rp_pass():
    # Call the function
    out = check_hazard_rp(["2", "5", "10"])

    # Assert the output
    assert out == [2, 5, 10]


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


def test_check_hazard_types_fail():
    # Call the function with a missing entry
    with pytest.raises(
        FIATDataError,
        match="Missing mandatory hazard types",
    ):
        check_hazard_types(
            types=["foo"],
            mandatory_types=["foo", "bar"],
        )

    # Call the function but with too many foo's compared to bar
    with pytest.raises(
        FIATDataError,
        match="Different number of datasets per type",
    ):
        check_hazard_types(
            types=["foo", "foo", "bar"],
            mandatory_types=["foo", "bar"],
        )


def test_check_hazard_types_pass():
    # Call the function
    out = check_hazard_types(
        types=["foo", "bar", "bar", "foo", "bar", "foo"],
        mandatory_types=["foo", "bar"],
    )

    # Assert the output
    assert out == [[0, 3, 5], [1, 2, 4]]


def test_check_input_data_pass():
    # Call the function
    check_input_data(["foo", 2, int])


def test_check_input_data_container_pass():
    # Create a container
    c = Container()
    c.set(2)
    # Call the function
    check_input_data(["foo", c, int])


def test_check_input_data_fail():
    with pytest.raises(
        TypeError,
        match="foo is incorrectly set, currently of type int",
    ):
        # Call the function with the wrong type
        check_input_data(["foo", 2, str])

    with pytest.raises(
        TypeError,
        match="foo is incorrectly set, currently of type NoneType",
    ):
        # Call the function when None
        check_input_data(["foo", None, str])


def test_check_input_data_container_fail():
    # Create an empty container
    c = Container()
    with pytest.raises(
        ValueError,
        match="foo is empty",
    ):
        # Call the function with the wrong type
        check_input_data(["foo", c, str])

    c.set(2)
    with pytest.raises(
        TypeError,
        match="Wrong type encountered in foo",
    ):
        # Call the function when None
        check_input_data(["foo", c, str])


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


def test_check_vs_srs_fail(
    srs_4326: osr.SpatialReference,
    srs_3857: osr.SpatialReference,
):
    # Call the function with the different srs
    b = check_vs_srs(srs_4326, srs_3857)

    # Assert the output
    assert not b


def test_check_vs_srs_pass(srs_4326: osr.SpatialReference):
    # Call the function with the different srs
    b = check_vs_srs(srs_4326, srs_4326)

    # Assert the output
    assert b
