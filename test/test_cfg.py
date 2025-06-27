from pathlib import Path

from fiat.cfg import Configurations


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


def test_configuration_path(testdata_dir: Path):
    # Create the object
    c = Configurations(
        **{
            "_root": testdata_dir,
            "foo.file": "path.txt",
            "hazard.file": "hazard/event_map.nc",  # Actual needed path by the model
        }
    )

    # Assert the state
    assert isinstance(c.get("foo.file"), str)
    assert isinstance(c.get("hazard.file"), Path)
    assert c.get("hazard.file").is_absolute()


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
    assert "hazard.file" in c
    assert "exposure.geom.file1" in c
    assert "vulnerability.file" in c


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


def test_configuration_setup_output_dir_grid(testdata_dir: Path, tmp_path: Path):
    # Create the object
    c = Configurations(
        _root=testdata_dir,
        model={"risk": True},
        exposure={"grid": {"file": "exposure/spatial.nc"}},
    )

    # Call the method
    c.setup_output_dir(Path(tmp_path, "output"))

    # Assert the directory
    assert Path(tmp_path, "output").is_dir()
    assert Path(tmp_path, "output", "damages").is_dir()


def test_configuration_update():
    # Create the object
    c = Configurations()
    # Assert current
    assert c.get("foo.bar") is None

    # Call the method
    c.update({"foo.bar": "baz"})

    # Assert the state
    assert c.get("foo.bar") == "baz"
