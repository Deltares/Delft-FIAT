import time
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from osgeo import osr

from fiat.fio import GridIO
from fiat.util import (
    GEOM_DRIVER_MAP,
    GRID_DRIVER_MAP,
    DummyLock,
    DummyWriter,
    _diff_table,
    _load_diff,
    deter_dec,
    deter_type,
    distribute_threads,
    find_duplicates,
    flatten_dict,
    generic_directory_check,
    generic_path_check,
    get_module_attr,
    get_srs_repr,
    mean,
    object_size,
    re_filter,
    read_gridsource_info,
    read_gridsource_layers,
    regex_pattern,
    replace_empty,
    text_chunk_gen,
    timeit,
)


def test__load_diff():
    # Call the function
    rl = _load_diff(size=100000, threads=5, diff=-1, max_threads=8)
    rm = _load_diff(size=100000, threads=5, diff=1, max_threads=8)

    # Assert the output
    assert int(rl) == 5000
    assert int(rm) == 3333


def test__load_diff_inf():
    # Call the function going below 1
    r = _load_diff(size=100000, threads=1, diff=-1, max_threads=8)

    # Assert the output
    assert r == np.inf


def test__load_diff_zero():
    # Call the function going over the max
    r = _load_diff(size=100000, threads=8, diff=1, max_threads=8)

    # Assert the output
    assert r == 0


def test__diff_table():
    # Call the function
    f, d = _diff_table(
        sizes=[100000, 4000, 20000, 50],
        threads_diss=[5, 1, 1, 1],
        max_threads=8,
    )

    # Assert the output
    assert np.sum(f) == 1
    assert f[2, 0] == 1
    assert int(d[2, 0]) == 5000
    assert d[2, 1] == np.inf


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


def test_distribute_threads():
    # Call the function
    t = distribute_threads(
        size=[100000, 4000, 20000, 50],
        threads=8,
    )

    # Assert the output
    assert t == [4, 1, 2, 1]


def test_distribute_threads_single():
    # Call the function
    t = distribute_threads(
        size=[100000],
        threads=8,
    )

    # Assert the output
    assert t == [8]


def test_distribute_threads_one():
    # Call the function
    t = distribute_threads(
        size=[100000, 4000, 20000, 50],
        threads=1,
    )

    # Assert the output
    assert t == [1, 1, 1, 1]


def test_distribute_threads_fill():
    # Call the function
    t = distribute_threads(
        size=[100000, 25000, 25000],
        threads=8,
    )

    # Assert the output
    assert t == [4, 2, 2]


def test_driver_maps():
    # Simply assert some key drivers
    assert ".gpkg" in GEOM_DRIVER_MAP
    assert ".tif" not in GEOM_DRIVER_MAP
    assert ".nc" in GEOM_DRIVER_MAP
    assert ".nc" in GRID_DRIVER_MAP
    assert ".fgb" not in GRID_DRIVER_MAP


def test_dummy_lock():
    # Create the object
    l = DummyLock()

    # Empty so calling the methods shouldnt do anything
    l.acquire()
    l.release()


def test_dummy_writer():
    # Create the object
    w = DummyWriter()

    # Empty so calling the methods shouldnt do anything
    w.add()
    w.add_iterable()
    w.close()


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


def test_generic_directory_check(tmp_path: Path):
    # Create a path an assert it's state
    new_dir = Path("output")
    assert new_dir.is_absolute() == False
    assert Path(tmp_path, new_dir).exists() == False

    # Call the function
    new_dir = generic_directory_check(path=new_dir, root=tmp_path)

    # Assert the properties and existence of the directory
    assert new_dir.exists()
    assert new_dir.is_absolute()


def test_generic_directory_check_exist(tmp_path: Path):
    # Create a path an assert it's state
    assert tmp_path.exists()

    # Call the function
    new_dir = generic_directory_check(path=tmp_path)

    # Assert the properties and existence of the directory
    assert new_dir == tmp_path
    assert new_dir.exists()


def test_get_module_attr():
    # Call the function
    attr = get_module_attr("fiat.method.flood.depth", "NEW_COLUMNS")
    # Assert the output
    assert attr == ["depth"]


def test_get_srs_repr(srs_4326: osr.SpatialReference):
    # Call the function
    r = get_srs_repr(srs_4326)

    # Assert the output
    assert r == "EPSG:4326"


def test_get_srs_repr_proj():
    srs = osr.SpatialReference()
    srs.ImportFromProj4("+proj=longlat +datum=WGS84 +no_defs +type=crs")
    # Call the function
    r = get_srs_repr(srs)

    # Assert the output
    assert r.startswith("+proj")


def test_get_srs_repr_error():
    # Call the function with no srs as input
    with pytest.raises(
        ValueError,
        match="'srs' can not be None.",
    ):
        _ = get_srs_repr(None)


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


def test_gridsource_layers_multi(hazard_risk_data_subsets: GridIO):
    # Call the function
    layers = read_gridsource_layers(hazard_risk_data_subsets.src)
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
    assert len(elem) == 46

    # Call the function
    pat = regex_pattern(delimiter=",", multi=True)
    elem = pat.split(data)
    # Assert the output
    assert len(elem) == 70


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


def test_text_chunk_gen_res():
    # Setup a buffer
    buffer = BytesIO()
    buffer.write(b"1,2,3,4\n2,3,4,5")
    buffer.seek(0)
    # Setup a pattern
    pat = regex_pattern(",", multi=True)

    # Call the function
    cg = text_chunk_gen(
        buffer,
        pattern=pat,
        chunk_size=100,
    )
    # Make a list out of it
    cg = list(cg)

    # Assert the output
    assert len(cg) == 2
    assert cg[0][0] == 0
    assert cg[1][1] == [b"2", b"3", b"4", b"5"]


def test_text_chunk_gen_single():
    # Setup a buffer
    buffer = BytesIO()
    buffer.write(b"1,2,3,4")
    buffer.seek(0)
    # Setup a pattern
    pat = regex_pattern(",", multi=True)

    # Call the function
    cg = text_chunk_gen(
        buffer,
        pattern=pat,
        chunk_size=100,
    )
    # Make a list out of it
    cg = list(cg)

    # Assert the output
    assert len(cg) == 1
    assert cg[0][0] == 0


@timeit(n=20)
def func_dummy1():
    time.sleep(0.001)


@timeit(n=100)
def func_dummy2():
    time.sleep(0.001)


def test_timeit():
    # Call the functions
    t1 = func_dummy1()
    t2 = func_dummy2()

    # t2 should take longer
    assert t2 > 2 * t1
