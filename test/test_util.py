from pathlib import Path

import numpy as np
import pytest

from fiat.fio import GridIO
from fiat.util import (
    GEOM_READ_DRIVER_MAP,
    GEOM_WRITE_DRIVER_MAP,
    GRID_DRIVER_MAP,
    create_1d_chunk,
    create_dir,
    create_windows,
    deter_dec,
    deter_type,
    discover_exp_columns,
    find_duplicates,
    flatten_dict,
    generate_output_columns,
    generic_path_check,
    get_module_attr,
    mean,
    object_size,
    re_filter,
    read_gridsource_info,
    read_gridsource_layers,
    regex_pattern,
    replace_empty,
    text_chunk_gen,
)


def test_create_1d_chunk_few():
    # Call the function
    chunks = list(create_1d_chunk(500, 6))

    # Assert the output
    assert len(chunks) == 6
    assert chunks[0] == (1, 84)
    assert chunks[-1] == (421, 500)


def test_create_1d_chunk_many():
    # Call the function
    chunks = list(create_1d_chunk(500, 20))

    # Assert the output
    assert len(chunks) == 20
    assert chunks[0] == (1, 25)
    assert chunks[-1] == (476, 500)


def test_create_dir(tmp_path: Path):
    # Create a path an assert it's state
    new_dir = Path("output")
    assert new_dir.is_absolute() == False
    assert Path(tmp_path, new_dir).exists() == False

    # Call the function
    new_dir = create_dir(root=tmp_path, path=new_dir)

    # Assert the properties and existence of the directory
    assert new_dir.exists()
    assert new_dir.is_absolute()


def test_create_windows_even():
    # Call the function
    windows = list(create_windows((10, 10), (2, 2)))

    # Assert the output
    assert len(windows) == 25
    assert windows[0] == (0, 0, 2, 2)
    assert windows[-1] == (8, 8, 2, 2)  # Should nicely fit


def test_create_windows_uneven():
    # Call the function
    windows = list(create_windows((10, 10), (4, 4)))
    assert len(windows) == 9
    assert windows[0] == (0, 0, 4, 4)
    assert windows[-1] == (8, 8, 2, 2)  # It's the same as it does not fit


def test_deter_dec():
    # Call the function
    out = deter_dec(0.00001)
    # Assert the output
    assert out == 5

    # Call the function
    out = deter_dec(0.01)
    # Assert the output
    assert out == 2


def test_deter_type():
    out = deter_type(b"2\n2\n2", l=2)
    assert out == 1  # Integers

    out = deter_type(b"2.2\n2\n2", l=2)
    assert out == 2  # Floating point number

    out = deter_type(b"2\n\n2", l=2)
    assert out == 2  # Floating point number (int cant have nan)

    out = deter_type(b"2\n2\ntext", l=2)
    assert out == 3  # strings

    out = deter_type(b"2\n2\n2", l=5)
    assert out == 3  # Cannot solve, default to string


def test_discover_columns_found(exposure_cols: dict):
    # Call the function
    dmg_suffix, dmg_idx, missing = discover_exp_columns(exposure_cols, type="damage")
    assert dmg_suffix == ["_structure", "_content"]
    assert dmg_idx["fn"]["_content"] == 2
    assert dmg_idx["max"]["_content"] == 4
    assert len(missing) == 0


def test_discover_columns_missing(exposure_cols: dict):
    # Pop an entry for max damage
    _ = exposure_cols.pop("max_damage_content")
    # Call the function
    dmg_suffix, dmg_idx, missing = discover_exp_columns(exposure_cols, type="damage")
    assert dmg_suffix == ["_structure"]
    assert dmg_idx["fn"]["_structure"] == 1
    assert dmg_idx["max"]["_structure"] == 3
    assert missing == ["_content"]


def test_driver_maps():
    # Simply assert some key drivers
    assert ".gpkg" in GEOM_WRITE_DRIVER_MAP
    assert ".nc" not in GEOM_WRITE_DRIVER_MAP
    assert ".nc" in GEOM_READ_DRIVER_MAP
    assert ".nc" in GRID_DRIVER_MAP


def test_find_duplicated():
    # Assert no duplicates
    data = [1, 2, 3, 4]
    # Call the function
    res = find_duplicates(data)
    assert res is None

    # Assert one duplicate
    data.append(1)
    # Call the function
    res = find_duplicates(data)
    assert res is not None
    assert res == [1]

    # Assert two duplicates
    data += [5, 5]
    # Call the function
    res = find_duplicates(data)
    assert res == [1, 5]


def test_flatten_dict():
    # Test a dictionary that cannot be flattened
    data = {"entry1": "stuff", "entry2": "stuff"}
    # Call the function
    flattened = flatten_dict(data)
    assert "entry2" in flattened  # nothing happened

    # Dictionary that can the flattened
    data = {"entry1": "stuff", "entry2": {"sub1": "stuff"}}
    # Call the function
    flattened = flatten_dict(data)
    # Assert the output
    assert "entry2" not in flattened
    assert "entry2.sub1" in flattened


def test_generate_output_columns(exposure_data_fn: dict):
    # Call the function
    new_fields, len1, total_idx = generate_output_columns(
        specific_columns=["inun_depth"],
        exposure_types={"damage": exposure_data_fn},
    )

    # Assert the output
    assert len(new_fields) == 4
    assert new_fields[2] == "damage_structure"
    assert len1 == 4
    assert total_idx[0] == -1


def test_generate_output_columns_extra(exposure_data_fn: dict):
    # Call the function
    new_fields, len1, _ = generate_output_columns(
        specific_columns=["inun_depth"],
        exposure_types={"damage": exposure_data_fn},
        extra=["ead"],
    )

    # Assert the output
    assert len1 == 5
    assert new_fields[-1] == "ead_damage"


def test_generate_output_columns_multi(exposure_data_fn: dict):
    # Call the function
    new_fields, len1, _ = generate_output_columns(
        specific_columns=["inun_depth"],
        exposure_types={"damage": exposure_data_fn},
        extra=["ead"],
        suffix=["1", "2"],
    )

    # Assert the output
    assert len1 == 4
    assert len(new_fields) == 9
    assert new_fields[4] == "inun_depth_2"


def test_generic_path_check(
    testdata_dir: Path,
):
    # Call the function
    p = generic_path_check("geom_event.toml", root=testdata_dir)
    # Assert the output
    assert p == Path(testdata_dir, "geom_event.toml")

    # Call the function on absolute path
    p = generic_path_check(Path(testdata_dir, "geom_event.toml"), root=testdata_dir)
    # Assert the output
    assert p == Path(testdata_dir, "geom_event.toml")


def test_generic_path_check_error(
    tmp_path: Path,
):
    p = Path(tmp_path, "tmp.unknown")
    # Call the function while the path doesnt exist
    with pytest.raises(
        FileNotFoundError,
        match=f"{p.as_posix()} is not a valid path",
    ):
        generic_path_check(p, root=tmp_path)


def test_get_module_attr():
    # Call the function
    attr = get_module_attr("fiat.methods.flood", "NEW_COLUMNS")
    # Assert the output
    assert attr == ["inun_depth"]


def test_gridsource_info(hazard_event_data: GridIO):
    # Call the function
    data = read_gridsource_info(hazard_event_data.src)

    # Assert the output
    assert data["driverShortName"] == "netCDF"


def test_gridsource_layers_single(hazard_event_data: GridIO):
    # Call the function
    layers = read_gridsource_layers(hazard_event_data.src)

    # Assert the output
    assert layers is None


def test_gridsource_layers_multi(hazard_risk_sub_data: GridIO):
    # Call the function
    layers = read_gridsource_layers(hazard_risk_sub_data.src)
    assert len(layers) == 4
    subpath = layers["Band4"]
    assert subpath.startswith("NETCDF")
    assert subpath.endswith("Band4")


def test_mean():  # dunb function, dumb test
    # Call the function
    x = mean([1, 2, 3, 4])
    assert int(x * 100) == 250

    # Call the function
    y = mean([2, 6, 10, 1])
    assert int(y * 100) == 475


def test_object_size():
    # Call the function
    size = object_size(44)
    assert size == 28

    # Call the function
    size = object_size(4.4)
    assert size == 24

    # Call the function
    size = object_size(np.array([]))
    assert size == 112

    # Call the function
    size = object_size(np.array([2, 2, 2]))
    assert size == 136


def test_re_filter():
    # Call the function with an element that cannot be matched
    filt = re_filter(
        values=["fn_damage", "fn_damage_structure", "something_else"],
        pat=r"^fn_damage(_\w+)?$",
    )

    # Assert the output
    assert len(filt) == 2
    assert "fn_damage" in filt


def test_re_filter_edge():
    # Edge case: only underscore after the normal characters
    # Call the function
    filt = re_filter(
        values=["fn_damage", "fn_damage_"],
        pat=r"^fn_damage(_\w+)?$",
    )
    assert len(filt) == 1
    assert "fn_damage_" not in filt


def test_regex_pattern(vulnerability_path: Path):
    # Open the data as binary
    with open(vulnerability_path, "rb") as r:
        data = r.read()

    # Call the function
    pat = regex_pattern(delimiter=",")
    elem = pat.split(data)
    # Assert the output
    assert len(elem) == 47

    # Call the function
    pat = regex_pattern(delimiter=",", multi=True)
    elem = pat.split(data)
    # Assert the output
    assert len(elem) == 71


def test_regex_pattern_other(vulnerability_path: Path):
    # Open the data as binary
    with open(vulnerability_path, "rb") as r:
        data = r.read()

    # Call the function
    pat = regex_pattern(delimiter=";")
    elem = pat.split(data)
    # Assert the output
    assert len(elem) == 1

    # Call the function
    pat = regex_pattern(delimiter=";", multi=True)
    elem = pat.split(data)
    # Assert the output
    assert len(elem) == 25

    # Call the function
    pat = regex_pattern(delimiter=";", multi=True, nchar=b"\r\n")
    elem = pat.split(data)
    # Assert the output
    assert len(elem) == 1


def test_replace_emptry():
    # Call the function
    out = replace_empty([b"1", b"2", b"3"])
    # Assert the output
    assert out == ["1", "2", "3"]

    # Call the function
    out = replace_empty([b"1", b"2", b""])
    # Assert the output
    assert out == ["1", "2", "nan"]


def test_text_chunk_gen(vulnerability_path: Path):
    # Get a stream handler
    data = open(vulnerability_path, "rb")
    # Setup a pattern
    pat = regex_pattern(",", multi=True)

    # Call the function
    cg = text_chunk_gen(
        data,
        pattern=pat,
        chunk_size=100,
    )
    # Make a list out of it
    cg = list(cg)

    # Assert the output
    assert len(cg) == 4
    assert cg[0][0] == 5
    assert cg[3][0] == 3
