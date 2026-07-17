from pathlib import Path

from fiat.cfg import Configurations, get_item, set_item


def test_get_item():
    # Call the function
    out = get_item(
        parts=["foo", "bar"],
        current={"foo": {"bar": 2}},
    )

    # Assert output
    assert out == 2


def test_get_item_iter():
    # Call the function
    out = get_item(
        parts=["foo", "bar", "value"],
        current={"foo": {"bar": [{"value": 1}, {"value": 2}]}},
    )

    # Assert output
    assert out == [1, 2]


def test_get_item_out():
    # Call the function
    out = get_item(
        parts=["foo", "baz"],
        current={"foo": {"bar": 2}},
    )

    # Assert output
    assert out is None


def test_get_item_fallback():
    # Call the function
    out = get_item(
        parts=["foo", "baz"],
        current={"foo": {"bar": 2}},
        fallback=3,
    )

    # Assert output
    assert out == 3


def test_set_item():
    # Call the function
    c = {}
    set_item(
        parts=["foo", "bar"],
        current=c,
        value=2,
    )

    # Assert the state
    assert "foo" in c
    assert c["foo"]["bar"] == 2


def test_set_item_overwrite():
    # Call the function
    c = {"foo": 3}
    set_item(
        parts=["foo", "bar"],
        current=c,
        value=2,
    )

    # Assert the state
    assert "bar" in c["foo"]
    assert c["foo"]["bar"] == 2


def test_configuration_empty():
    # Create the object
    c = Configurations()

    # Assert some simple stuff
    assert isinstance(c.path, Path)
    assert isinstance(c.filepath, Path)
    assert c.filepath.as_posix() == "< Configurations-in-memory >"


def test_configuration_implicit(tmp_path: Path):
    # Create the object
    c = Configurations(
        _root=tmp_path,
        _name="tmp.toml",
    )

    # Assert the state
    assert c.path == tmp_path
    assert c.filepath == Path(tmp_path, "tmp.toml")


def test_configuration_output(tmp_path: Path):
    # Create the object
    c = Configurations(
        _root=tmp_path,
    )

    # Assert the existing directory
    assert c.get("output.path") == Path(tmp_path, "output")


def test_configuration_from_file(testdata_dir: Path):
    # Create the object
    c = Configurations.from_file(
        Path(testdata_dir, "geom_event.toml"),
    )

    # Assert the content
    assert c.path == testdata_dir
    assert c.get("hazard.file") is not None


def test_configuration_generate_kwargs():
    # Create the object
    c = Configurations(
        foo={
            "file": "bar.txt",
            "settings": {
                "baz": "oof",
                "spooky": "ghost",
            },
        },
    )

    # Call the method
    kw = c.generate_kwargs("foo.settings")

    # Assert the output
    assert kw == {"baz": "oof", "spooky": "ghost"}


def test_configuration_generate_kwargs_empty():
    # Create the object
    c = Configurations(foo=2)

    # Call the method
    kw = c.generate_kwargs("foo")

    # Assert the output
    assert kw == {}
    assert len(kw) == 0


def test_configuration_set():
    # Create the object
    c = Configurations()
    # Assert current
    assert c.get("foo.bar") is None

    # Call the method
    c.set("foo.bar", "baz")

    # Assert the state
    assert c.get("foo.bar") == "baz"


def test_configuration_setup_output_dir(tmp_path: Path):
    # Create the object
    c = Configurations(
        _root=tmp_path,
    )

    # Call the method
    c.setup_output_dir()

    # Assert the directory
    assert Path(tmp_path, "output").is_dir()

    # Call the method with argument
    c.setup_output_dir("foo")

    # Assert the directory
    assert Path(tmp_path, "foo").is_dir()
    assert c.get("output.path") == Path(tmp_path, "foo")


def test_configuration_update():
    # Create the object
    c = Configurations()
    # Assert current
    assert c.get("foo.bar") is None

    # Call the method
    c.update({"foo": {"bar": "baz"}})

    # Assert the state
    assert c.get("foo.bar") == "baz"
