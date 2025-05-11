from pathlib import Path

import pytest

from fiat.fio.buffer import BufferedGeomWriter, BufferedTextWriter
from fiat.fio.geom import GeomIO
from fiat.util import DummyLock


def test_buffered_geom_writer_create(tmp_path: Path, exposure_geom_dataset: GeomIO):
    p = Path(tmp_path, "tmp.geojson")
    # Create the writer
    w = BufferedGeomWriter(
        p,
        srs=exposure_geom_dataset.srs,
        layer_defn=exposure_geom_dataset.layer.defn,
        buffer_size=2,  # two features
    )

    # Assert some simple stuff
    assert w.max_size == 2
    assert isinstance(w.lock, DummyLock)
    assert isinstance(w.buffer, GeomIO)
    assert w.buffer.path.as_posix() == "/vsimem/tmp.gpkg"

    # Check for the error when there is no file and no layer defn is given
    with pytest.raises(OSError, match=f"Cannot create {p} in 'read' mode."):
        w = BufferedGeomWriter(
            p,
            srs=exposure_geom_dataset.srs,
            layer_defn=None,
            buffer_size=2,  # two features
        )

    # Clear the data
    w.close()


def test_buffered_geom_writer_create_fields(
    tmp_path: Path,
    exposure_geom_dataset: GeomIO,
):
    p = Path(tmp_path, "tmp.geojson")
    # Create the writer
    w = BufferedGeomWriter(
        p,
        srs=exposure_geom_dataset.srs,
        layer_defn=exposure_geom_dataset.layer.defn,
        buffer_size=2,  # two features
    )

    # Assert the current fields
    assert w.buffer.layer.fields == ["object_id", "object_name"]

    # Create some fields
    w.create_fields(zip(["foo"], [0]))

    # Assert that is has been added
    assert w.buffer.layer.fields == ["object_id", "object_name", "foo"]

    # Clear the data
    w.close()


def test_buffered_geom_writer_write(tmp_path: Path, exposure_geom_dataset: GeomIO):
    p = Path(tmp_path, "tmp.geojson")
    # Create the dataset to write to
    with GeomIO(
        p,
        mode="w",
    ) as _w:
        _w.create_layer(
            exposure_geom_dataset.srs,
            geom_type=exposure_geom_dataset.layer.geom_type,
        )
        _w.layer.set_from_defn(exposure_geom_dataset.layer.defn)
    # Create the writer
    w = BufferedGeomWriter(
        p,
        srs=exposure_geom_dataset.srs,
        layer_defn=None,  # Infer from the dataset on the drive
        buffer_size=2,  # two features
    )

    # Assert the size of the buffer
    assert w.buffer.layer.size == 0

    w.add_feature_with_map(exposure_geom_dataset.layer[0], fmap={})
    # Assert size of the buffer
    assert w.buffer.layer.size == 1

    w.add_feature_with_map(exposure_geom_dataset.layer[1], fmap={})
    # Assert size of the buffer
    assert w.buffer.layer.size == 2
    w.add_feature_with_map(exposure_geom_dataset.layer[2], fmap={})
    # Assert size of the buffer
    assert w.buffer.layer.size == 1

    # Close the data
    w.close()


def test_buffered_geom_writer_write_direct(
    tmp_path: Path, exposure_geom_dataset: GeomIO
):
    p = Path(tmp_path, "tmp.geojson")
    # Create the dataset to write to
    assert p.is_file()


def test_buffered_text_writer_create(tmp_path: Path):
    p = Path(tmp_path, "tmp.txt")
    # Create the writer
    w = BufferedTextWriter(p, buffer_size=20)  # 20 chars

    # Assert some simple stuff
    assert isinstance(w.lock, DummyLock)
    assert w.max_size == 20


def test_buffered_text_writer_write(tmp_path: Path):
    p = Path(tmp_path, "tmp.txt")
    # Create the writer
    w = BufferedTextWriter(p, buffer_size=20)  # 20 chars

    # Write something to the buffer
    w.write(b"foo,bar,baz,var\n")  # 16 chars

    # Assert its in the buffer
    assert w.tell() == 16
    assert w.getbuffer().nbytes == 16  # Or more technical

    # Verify the content
    w.seek(0)  # Go the the start of the buffer
    content = w.read()
    assert content == b"foo,bar,baz,var\n"

    # Write more to the buffer
    w.write(b"foo,bar,baz\n")  # 12 chars

    # This should have triggerd a dump as 16 + 12 > 20
    assert w.tell() == 12

    # Flush the buffer when done, (also called in `close`)
    w.to_drive()

    # Assert that it is empty
    assert w.tell() == 0
    assert w.getbuffer().nbytes == 0

    # Close it
    w.close()


def test_buffered_text_writer_write_iterable(tmp_path: Path):
    p = Path(tmp_path, "tmp.txt")
    # Create the writer
    w = BufferedTextWriter(p, buffer_size=20)  # 20 chars

    # Write something to the buffer
    w.write_iterable(["foo", "bar", "baz", "var"])  # 16 chars (newline included)

    # Assert its in the buffer
    assert w.tell() == 16
    assert w.getbuffer().nbytes == 16  # Or more technical

    # Verify the content
    w.seek(0)  # Go the the start of the buffer
    content = w.read()
    assert content == b"foo,bar,baz,var\n"
