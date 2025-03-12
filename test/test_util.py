import copy
import shutil
import sys
from pathlib import Path

import numpy as np

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
    read_gridsource_info,
    read_gridsource_layers,
    regex_pattern,
    replace_empty,
)


def test_create_1d_chunk():
    length = 500
    parts = 6
    chunks = list(create_1d_chunk(length, parts))
    assert len(chunks) == 6
    assert chunks[0] == (1, 84)
    assert chunks[-1] == (421, 500)

    parts = 20
    chunks = list(create_1d_chunk(length, parts))
    assert len(chunks) == 20
    assert chunks[0] == (1, 25)
    assert chunks[-1] == (476, 500)


def test_create_dir(tmp_path):
    new_dir = Path("output")
    assert new_dir.is_absolute() == False
    assert Path(tmp_path, new_dir).exists() == False
    new_dir = create_dir(root=tmp_path, path=new_dir)
    assert new_dir.exists()
    assert new_dir.is_absolute()


def test_create_windows():
    shape = (10, 10)
    chunk = (2, 2)
    windows = list(create_windows(shape, chunk))
    assert len(windows) == 25
    assert windows[0] == (0, 0, 2, 2)
    assert windows[-1] == (8, 8, 2, 2)  # Should nicely fit

    chunk = (4, 4)
    windows = list(create_windows(shape, chunk))
    assert len(windows) == 9
    assert windows[0] == (0, 0, 4, 4)
    assert windows[-1] == (8, 8, 2, 2)  # It's the same as it does not fit


def test_deter_dec():
    out = deter_dec(0.00001)
    assert out == 5

    out = deter_dec(0.01)
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


def test_discover_columns(geom_partial_data):
    cols = copy.deepcopy(geom_partial_data._columns)
    dmg_suffix, dmg_idx, missing = discover_exp_columns(cols, type="damage")
    assert dmg_suffix == ["structure"]
    assert dmg_idx["fn"]["structure"] == 4
    assert dmg_idx["max"]["structure"] == 6
    assert missing == ["content"]

    cols["max_damage_content"] = 7
    dmg_suffix, dmg_idx, missing = discover_exp_columns(cols, type="damage")
    assert dmg_suffix == ["structure", "content"]
    assert len(missing) == 0


def test_driver_maps():
    assert ".gpkg" in GEOM_WRITE_DRIVER_MAP
    assert ".nc" not in GEOM_WRITE_DRIVER_MAP
    assert ".nc" in GEOM_READ_DRIVER_MAP
    assert ".nc" in GRID_DRIVER_MAP


def test_find_duplicated():
    data = [1, 2, 3, 4]
    res = find_duplicates(data)
    assert res is None

    data.append(1)
    res = find_duplicates(data)
    assert res is not None
    assert res == [1]

    data += [5, 5]
    res = find_duplicates(data)
    assert res == [1, 5]


def test_flatten_dict():
    data = {"entry1": "stuff", "entry2": "stuff"}
    flattened = flatten_dict(data)
    assert "entry2" in flattened  # nothing happened

    data = {"entry1": "stuff", "entry2": {"sub1": "stuff"}}
    flattened = flatten_dict(data)
    assert "entry2" not in flattened
    assert "entry2.sub1" in flattened


def test_generate_output_columns(geom_partial_data):
    dmg_suffix, dmg_idx, missing = discover_exp_columns(
        geom_partial_data._columns,
        type="damage",
    )
    new_fields, len1, total_idx = generate_output_columns(
        specific_columns=["inun_depth"],
        exposure_types={"damage": dmg_idx},
    )
    assert len(new_fields) == 4
    assert new_fields[2] == "damage_structure"
    assert len1 == 4
    assert total_idx[0] == -1

    new_fields, len1, total_idx = generate_output_columns(
        specific_columns=["inun_depth"],
        exposure_types={"damage": dmg_idx},
        extra=["ead"],
    )
    assert len1 == 5
    assert new_fields[-1] == "ead_damage"

    new_fields, len1, total_idx = generate_output_columns(
        specific_columns=["inun_depth"],
        exposure_types={"damage": dmg_idx},
        extra=["ead"],
        suffix=["1", "2"],
    )
    assert len1 == 4
    assert len(new_fields) == 9
    assert new_fields[4] == "inun_depth_2"


def test_generic_path_check(tmp_path, vul_path):
    _ = generic_path_check(vul_path, root=tmp_path)
    shutil.copy2(vul_path, Path(tmp_path, vul_path.name))
    path = generic_path_check(vul_path.name, tmp_path)
    assert path.is_absolute()

    try:
        file = "data.dat"
        _ = generic_path_check(file, tmp_path)
    except FileNotFoundError:
        t, v, tb = sys.exc_info()
        assert v.args[0].endswith("is not a valid path")
    finally:
        assert v


def test_get_model_attr():
    module = "fiat.methods.flood"
    attr = get_module_attr(module, "NEW_COLUMNS")
    assert attr == ["inun_depth"]


def test_gridsource_info(grid_event_data):
    data = read_gridsource_info(grid_event_data.src)
    assert data["driverShortName"] == "netCDF"


def test_gridsource_layers(grid_event_data, grid_risk_data):
    layers = read_gridsource_layers(grid_event_data.src)
    assert len(layers) == 0

    layers = read_gridsource_layers(grid_risk_data.src)
    assert len(layers) == 4
    subpath = layers["Band4"]
    assert subpath.startswith("NETCDF")
    assert subpath.endswith("Band4")


def test_mean():  # dunb function, dumb test
    x = mean([1, 2, 3, 4])
    assert int(x * 100) == 250

    y = mean([2, 6, 10, 1])
    assert int(y * 100) == 475


def test_object_size():
    size = object_size(44)
    assert size == 28

    size = object_size(4.4)
    assert size == 24

    size = object_size(np.array([]))
    assert size == 112

    size = object_size(np.array([2, 2, 2]))
    assert size == 136


def test_regex_pattern(vul_raw_data):
    pat = regex_pattern(delimiter=",")
    elem = pat.split(vul_raw_data)
    assert len(elem) == 47

    pat = regex_pattern(delimiter=",", multi=True)
    elem = pat.split(vul_raw_data)
    assert len(elem) == 71

    pat = regex_pattern(delimiter=";")
    elem = pat.split(vul_raw_data)
    assert len(elem) == 1

    pat = regex_pattern(delimiter=";", multi=True)
    elem = pat.split(vul_raw_data)
    assert len(elem) == 25

    pat = regex_pattern(delimiter=";", multi=True, nchar=b"\r\n")
    elem = pat.split(vul_raw_data)
    assert len(elem) == 1


def test_replace_emptry():
    data = [b"1", b"2", b"3"]
    out = replace_empty(data)
    assert out == ["1", "2", "3"]

    data[2] = b""
    out = replace_empty(data)
    assert out == ["1", "2", "nan"]
