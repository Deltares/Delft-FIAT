from multiprocessing import get_context
from multiprocessing.synchronize import Lock
from pathlib import Path

from osgeo import ogr

from fiat.fio.buffer import BufferedGeomWriter, BufferedTextWriter
from fiat.fio.geom import GeomIO
from fiat.util import NEWLINE_CHAR, DummyLock


def test_buffered_geom_writer_init(tmp_path: Path):
    p = Path(tmp_path, "tmp.geojson")
    # Create the writer
    w = BufferedGeomWriter(
        p,
        buffer_size=2,  # two features
    )

    # Assert some simple stuff
    assert w.max_size == 2
    assert isinstance(w.lock, DummyLock)
    assert isinstance(w.buffer, GeomIO)
    assert w.buffer.path.as_posix() == "/vsimem/tmp.gpkg"

    # Clear the data
    w.close()


def test_buffered_geom_writer_init_lock(tmp_path: Path):
    p = Path(tmp_path, "tmp.geojson")
    # Create the writer
    w = BufferedGeomWriter(
        p,
        lock=Lock(ctx=get_context()),
    )

    # Assert some simple stuff
    assert isinstance(w.lock, Lock)
    assert isinstance(w.buffer, GeomIO)

    # Clear the data
    w.close()


def test_buffered_geom_writer_setup_layer(
    tmp_path: Path,
    exposure_geom_dataset: GeomIO,
):
    p = Path(tmp_path, "tmp.geojson")
    # Create the writer
    w = BufferedGeomWriter(
        p,
        buffer_size=2,  # two features
    )
    # Assert the current state
    assert w.buffer.layer is None

    # Setup the (buffer) layer
    w.setup(
        defn=exposure_geom_dataset.layer.defn,
        srs=exposure_geom_dataset.srs,
    )

    # Assert the state
    assert w.buffer.layer is not None
    assert "object_id" in w.buffer.layer.fields

    # Close the data
    w.close()


def test_buffered_geom_writer_setup_layer_with_fields(
    tmp_path: Path,
    exposure_geom_dataset: GeomIO,
):
    p = Path(tmp_path, "tmp.geojson")
    # Create the writer
    w = BufferedGeomWriter(
        p,
        buffer_size=2,  # two features
    )
    # Assert the current state
    assert w.buffer.layer is None
    assert len(exposure_geom_dataset.layer.fields) == 5

    # Setup the (buffer) layer
    w.setup(
        defn=exposure_geom_dataset.layer.defn,
        srs=exposure_geom_dataset.srs,
        extra_fields={"foo": 0},
    )

    # Assert the state
    assert w.buffer.layer is not None
    assert "object_id" in w.buffer.layer.fields
    assert len(w.buffer.layer.fields) == 6
    assert "foo" in w.buffer.layer.fields

    # Close the data
    w.close()


def test_buffered_geom_writer_add(
    tmp_path: Path,
    exposure_geom_dataset: GeomIO,
):
    p = Path(tmp_path, "tmp.geojson")
    # Create the writer
    w = BufferedGeomWriter(
        p,
        buffer_size=2,  # two features
    )
    # Create the layer like dummy
    w.buffer.create_layer(
        srs=exposure_geom_dataset.srs,
        geom_type=exposure_geom_dataset.layer.geom_type,
    )
    w.buffer.layer.set_from_defn(defn=exposure_geom_dataset.layer.defn)
    w.defn = exposure_geom_dataset.layer.defn

    # Create a feature that can be written directly
    ft = ogr.Feature(w.buffer.layer.defn)
    ft.SetFrom(exposure_geom_dataset.layer[0])

    # Set directly
    w.add_feature(ft)
    # Assert that it is in the buffer
    assert w.buffer.layer.size == 1


def test_buffered_geom_writer_add_write(
    tmp_path: Path,
    exposure_geom_dataset: GeomIO,
):
    p = Path(tmp_path, "tmp.geojson")
    # Create the writer
    w = BufferedGeomWriter(
        p,
        buffer_size=2,  # two features
    )
    # Create the layer like dummy
    w.buffer.create_layer(
        srs=exposure_geom_dataset.srs,
        geom_type=exposure_geom_dataset.layer.geom_type,
    )
    w.buffer.layer.set_from_defn(defn=exposure_geom_dataset.layer.defn)
    w.defn = exposure_geom_dataset.layer.defn

    # Create a feature that can be written directly
    ft = ogr.Feature(w.buffer.layer.defn)
    ft.SetFrom(exposure_geom_dataset.layer[0])

    # Add another feature
    w.add_feature(ft)
    ft.SetFID(2)
    w.add_feature(ft)
    ft.SetFID(3)
    w.add_feature(ft)
    # Assert its written as only one should be in the buffer
    assert w.buffer.layer.size == 1

    # Close the dataset
    w.close()


def test_buffered_geom_writer_add_with_map(
    tmp_path: Path,
    exposure_geom_dataset: GeomIO,
):
    p = Path(tmp_path, "tmp.geojson")
    # Create the writer
    w = BufferedGeomWriter(
        p,
        buffer_size=2,  # two features
    )
    # Create the layer like dummy
    w.buffer.create_layer(
        srs=exposure_geom_dataset.srs,
        geom_type=exposure_geom_dataset.layer.geom_type,
    )
    w.buffer.layer.set_from_defn(defn=exposure_geom_dataset.layer.defn)
    w.defn = exposure_geom_dataset.layer.defn

    # Assert the size of the buffer
    assert w.buffer.layer.size == 0

    w.add_feature_with_map(exposure_geom_dataset.layer[0], fmap={})
    # Assert size of the buffer
    assert w.buffer.layer.size == 1

    w.add_feature_with_map(exposure_geom_dataset.layer[1], fmap={})
    # Assert size of the buffer
    assert w.buffer.layer.size == 2
    w.add_feature_with_map(exposure_geom_dataset.layer[2], fmap={})
    # Assert size of the buffer after dumping
    assert w.buffer.layer.size == 1

    # Close the data
    w.close()


def test_buffered_text_writer_init(tmp_path: Path):
    p = Path(tmp_path, "tmp.txt")
    # Create the writer
    w = BufferedTextWriter(p, buffer_size=20)  # 20 chars

    # Assert some simple stuff
    assert isinstance(w.lock, DummyLock)
    assert w.max_size == 20


def test_buffered_text_writer_init_lock(tmp_path: Path):
    p = Path(tmp_path, "tmp.txt")
    # Create the writer
    w = BufferedTextWriter(
        p,
        lock=Lock(ctx=get_context()),
    )

    # Assert some simple stuff
    assert isinstance(w.lock, Lock)


def test_buffered_text_writer_write(tmp_path: Path):
    p = Path(tmp_path, "tmp.txt")
    # Create the writer
    w = BufferedTextWriter(p)

    # Add data like a dummy
    w.add(b"")

    # Write the buffer, (also called in `close`)
    w.write()

    # Assert that it is empty
    assert w.tell() == 0
    assert w.getbuffer().nbytes == 0

    # Close it
    w.close()


def test_buffered_text_writer_add(tmp_path: Path):
    p = Path(tmp_path, "tmp.txt")
    # Create the writer
    w = BufferedTextWriter(p, buffer_size=20)  # 20 chars

    # Write something to the buffer
    w.add(b"foo,bar,baz,var\n")  # 16 chars

    # Assert its in the buffer
    assert w.tell() == 16
    assert w.getbuffer().nbytes == 16  # Or more technical

    # Verify the content
    w.seek(0)  # Go the the start of the buffer
    content = w.read()
    assert content == b"foo,bar,baz,var\n"


def test_buffered_text_writer_add_write(tmp_path: Path):
    p = Path(tmp_path, "tmp.txt")
    # Create the writer
    w = BufferedTextWriter(p, buffer_size=20)  # 20 chars

    # Write more to the buffer
    w.add(b"foo,bar,baz,var\n")  # 16 chars
    w.add(b"foo,bar,baz\n")  # 12 chars

    # This should have triggerd a dump as 16 + 12 > 20
    assert w.tell() == 12


def test_buffered_text_writer_add_iterable(tmp_path: Path):
    p = Path(tmp_path, "tmp.txt")
    # Create the writer
    w = BufferedTextWriter(p, buffer_size=20)  # 20 chars

    # Write something to the buffer
    w.add_iterable(["foo", "bar", "baz", "var"])  # 16 chars (newline included)

    # Assert its in the buffer
    assert w.tell() == 15 + len(NEWLINE_CHAR)
    assert w.getbuffer().nbytes == 15 + len(NEWLINE_CHAR)  # Or more technical

    # Verify the content
    w.seek(0)  # Go the the start of the buffer
    content = w.read()
    assert content == f"foo,bar,baz,var{NEWLINE_CHAR}".encode()
