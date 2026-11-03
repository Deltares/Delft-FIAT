import re
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from pyproj import CRS

from fiat.check import (
    check_available_values,
    check_duplicate_columns,
    check_exp_cat_uniform,
    check_exp_cat_value,
    check_exp_cat_values,
    check_exp_columns,
    check_exp_derived_types,
    check_geom_extent,
    check_grid_exact,
    check_hazard_identifier,
    check_hazard_rp,
    check_hazard_subsets,
    check_hazard_types,
    check_input_data,
    check_internal_crs,
    check_vs_crs,
    check_vuln_axes,
    check_vuln_axis_types,
    check_vuln_categories,
    check_vuln_curve_ids,
    check_vuln_grid_method,
    check_vuln_group,
    check_vuln_method,
    check_vuln_types_keys,
    check_vuln_variables,
)
from fiat.container import Container
from fiat.error import FIATDataError
from fiat.log import Logger
from fiat.method import flood
from fiat.method.flood.depth import COLUMNS


def test_check_available_values_fail():
    # Call the function with a non available value
    with pytest.raises(
        FIATDataError,
        match=re.escape(
            "Dummy value: 'foo' invalid, chose from ['bar', 'baz']",
        ),
    ):
        check_available_values(
            value="foo",
            available=["bar", "baz"],
            msg="Dummy",
        )


def test_check_available_values_pass():
    # Call the function with the value available
    check_available_values(
        value="foo",
        available=["foo", "bar", "baz"],
        msg="Dummy",
    )


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
        match=re.escape("Missing mandatory exposure columns: ['elevation']"),
    ):
        check_exp_columns(
            ["object_id"],
            mandatory_columns=COLUMNS,
        )


def test_check_exp_columns_pass():
    # Call the function with all columns there
    check_exp_columns(
        ["object_id", "elevation"],
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
        "No every vulnerability curve has a corresponding \
maximum value: ['content']"
        in caplog.text
    )


def test_check_exp_cat_uniform_fail():
    # Category not in the category coordinate
    with pytest.raises(FIATDataError, match="Category 7"):
        check_exp_cat_uniform(
            layer="cat",
            value=7,
            value_var="foo",
            categories=[0, 1, 2],
        )


def test_check_exp_cat_uniform_pass():
    # Call the function with a known category
    check_exp_cat_uniform(
        layer="cat",
        value=1.0,
        value_var="foo",
        categories=[0, 1, 2],
    )


def test_check_exp_cat_value_fail():
    # Uniform category value variable
    with pytest.raises(FIATDataError, match="uniform"):
        check_exp_cat_value(
            layers={"cat": ["foo", "bar"]},
            uniform=["bar"],
        )

    # Category value variable shared between layers
    with pytest.raises(FIATDataError, match="foo"):
        check_exp_cat_value(
            layers={"cat1": ["foo", "bar"], "cat2": ["foo"]},
            uniform=[],
        )


def test_check_exp_cat_value_pass():
    # Call the function with distinct, non uniform value variables
    check_exp_cat_value(
        layers={"cat1": ["foo"], "cat2": ["bar"]},
        uniform=["baz"],
    )


def test_check_exp_cat_values_fail():
    # Call the function with a missing value variable
    with pytest.raises(FIATDataError, match=re.escape("['bar']")):
        check_exp_cat_values(
            layer="cat",
            values=["foo", "bar"],
            available=["cat", "foo"],
        )


def test_check_exp_cat_values_pass():
    # Call the function with all value variables present
    check_exp_cat_values(
        layer="cat",
        values=["foo"],
        available=["cat", "foo"],
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


def test_check_grid_exact_fail_crs(
    mocked_hazard_grid: MagicMock,
    mocked_exp_grid: MagicMock,
    caplog: Logger,
):
    # Set a different crs
    crs = CRS.from_epsg(3857)
    mocked_exp_grid.profile.crs = crs

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
    mocked_exp_grid.profile.transform = (0, 0.5, 0, 10, 0, -0.5)

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
    mocked_exp_grid.profile.shape = (5, 5)

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


def test_check_internal_crs_fail():
    # Call the function with no known crs
    with pytest.raises(
        FIATDataError,
        match=re.escape(
            "Coordinate reference system is unknown for 'tmp.nc', \
cannot safely continu"
        ),
    ):
        check_internal_crs(
            source_crs=None,
            fname="tmp.nc",
        )


def test_check_internal_crs_pass():
    # Call the function with a crs
    check_internal_crs(
        source_crs="EPSG:4326",
        fname="tmp.nc",
    )


def test_check_vs_crs_fail(
    crs_4326: CRS,
    crs_3857: CRS,
):
    # Call the function with the different crs
    b = check_vs_crs(crs_4326, crs_3857)

    # Assert the output
    assert not b


def test_check_vs_crs_pass(crs_4326: CRS):
    # Call the function with the different crs
    b = check_vs_crs(crs_4326, crs_4326)

    # Assert the output
    assert b


def test_check_vuln_axes_fail():
    # Not strictly increasing (decreasing and duplicate values)
    with pytest.raises(FIATDataError, match="depth_default"):
        check_vuln_axes("default", "depth_default", np.array([1.0, 0.5, 0.0]))
    with pytest.raises(FIATDataError, match="strictly increasing"):
        check_vuln_axes("default", "depth_default", np.array([0.0, 0.5, 0.5]))


def test_check_vuln_axes_pass():
    # Strictly increasing
    check_vuln_axes("default", "depth_default", np.array([0.0, 0.5, 1.0]))


def test_check_vuln_axis_types_fail():
    # Wrong axis type for a single dataset method
    with pytest.raises(FIATDataError, match="duration"):
        check_vuln_axis_types(
            "foo",
            axis_types=["duration"],
            method_axis_types=["water_depth"],
            ndatasets=1,
        )

    # Missing axis type (unknown)
    with pytest.raises(FIATDataError, match="foo"):
        check_vuln_axis_types(
            "foo",
            axis_types=[None],
            method_axis_types=["water_depth"],
            ndatasets=1,
        )

    # Too many axes for a combined method
    with pytest.raises(FIATDataError, match="foo"):
        check_vuln_axis_types(
            "foo",
            axis_types=["water_depth", "duration"],
            method_axis_types=["water_depth", "duration"],
            ndatasets=2,
        )

    # Axis type not in a combined method
    with pytest.raises(FIATDataError, match="foo"):
        check_vuln_axis_types(
            "foo",
            axis_types=["water_level"],
            method_axis_types=["water_depth", "duration"],
            ndatasets=2,
        )


def test_check_vuln_axis_types_pass():
    # Single dataset, order does not matter
    check_vuln_axis_types(
        "foo",
        axis_types=["duration", "water_depth"],
        method_axis_types=["water_depth", "duration"],
        ndatasets=1,
    )
    # One of the combined method axis types
    check_vuln_axis_types(
        "foo",
        axis_types=["duration"],
        method_axis_types=["water_depth", "duration"],
        ndatasets=2,
    )


def test_check_vuln_categories_fail():
    # Category 3 is missing from the dataset
    with pytest.raises(FIATDataError, match=re.escape("[3]")):
        check_vuln_categories(
            layer="cat",
            categories=[0, 1, 3],
            dataset="default",
            available=[1, 2],
        )


def test_check_vuln_categories_pass():
    # Category 0 is ignored
    check_vuln_categories(
        layer="cat",
        categories=[0, 1, 2],
        dataset="default",
        available=[1, 2],
    )


def test_check_vuln_curve_ids_fail():
    # Unknown curve id
    with pytest.raises(FIATDataError, match="'bar'"):
        check_vuln_curve_ids(
            layer="exp",
            curve_id="bar",
            dataset="default",
            available=["foo", "baz"],
        )


def test_check_vuln_curve_ids_pass():
    # Known curve id
    check_vuln_curve_ids(
        layer="exp",
        curve_id="foo",
        dataset="default",
        available=["foo", "baz"],
    )


def test_check_vuln_grid_method_fail():
    # flood.level needs a hazard conversion
    with pytest.raises(FIATDataError, match="flood.level"):
        check_vuln_grid_method(
            layer="exp",
            method="flood.level",
            types=flood.level.TYPES,
            axis_types=flood.level.AXIS_TYPES,
        )


def test_check_vuln_grid_method_pass():
    # flood.depth needs no hazard conversion
    check_vuln_grid_method(
        layer="exp",
        method="flood.depth",
        types=flood.depth.TYPES,
        axis_types=flood.depth.AXIS_TYPES,
    )


def test_check_vuln_group_fail():
    method_axis_types = ["water_depth", "duration"]
    # Wrong count
    with pytest.raises(FIATDataError, match="number of datasets"):
        check_vuln_group(
            layer="exp",
            method="flood.depth_duration",
            ndatasets=2,
            axis_types=["water_depth"],
            method_axis_types=method_axis_types,
        )

    # Duplicate axis types
    with pytest.raises(FIATDataError, match="duplicate"):
        check_vuln_group(
            layer="exp",
            method="flood.depth_duration",
            ndatasets=2,
            axis_types=["water_depth", "water_depth"],
            method_axis_types=method_axis_types,
        )

    # Axis types not equal to the method's
    with pytest.raises(FIATDataError, match="do not match"):
        check_vuln_group(
            layer="exp",
            method="flood.depth_duration",
            ndatasets=2,
            axis_types=["water_depth", "water_level"],
            method_axis_types=method_axis_types,
        )


def test_check_vuln_group_pass():
    # Order does not matter
    check_vuln_group(
        layer="exp",
        method="flood.depth_duration",
        ndatasets=2,
        axis_types=["duration", "water_depth"],
        method_axis_types=["water_depth", "duration"],
    )


def test_check_vuln_method_fail():
    # No method
    with pytest.raises(FIATDataError, match="no method"):
        check_vuln_method("foo", None)

    # Unknown method
    with pytest.raises(FIATDataError, match="flood.nope"):
        check_vuln_method("foo", "flood.nope")
    with pytest.raises(FIATDataError, match="nope.depth"):
        check_vuln_method("foo", "nope.depth")


def test_check_vuln_method_pass():
    # Known method
    check_vuln_method("foo", "flood.depth")


def test_check_vuln_types_keys_fail():
    # Unknown dimension
    with pytest.raises(FIATDataError, match=re.escape("['nope']")):
        check_vuln_types_keys(
            "direct",
            keys=["depth_direct", "nope"],
            dims=["depth_direct"],
        )


def test_check_vuln_types_keys_pass():
    # Known dimension
    check_vuln_types_keys("direct", keys=["depth_direct"], dims=["depth_direct"])


def test_check_vuln_variables_fail():
    # Unknown dataset
    with pytest.raises(FIATDataError, match=re.escape("['nope']")):
        check_vuln_variables(names=["default", "nope"], available=["default"])


def test_check_vuln_variables_pass():
    # Known dataset
    check_vuln_variables(names=["default"], available=["default", "direct"])
