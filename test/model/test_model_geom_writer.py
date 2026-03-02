from multiprocessing import get_context
from multiprocessing.synchronize import Lock
from pathlib import Path

from osgeo import ogr

from fiat.fio.geom import GeomIO
from fiat.model.geom_writer import GeomWriter
from fiat.util import DummyLock


def test_geom_writer_init(tmp_path: Path):
    p = Path(tmp_path, "tmp.geojson")
    # Create the writer
    w = GeomWriter(
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


def test_geom_writer_init_lock(tmp_path: Path):
    p = Path(tmp_path, "tmp.geojson")
    # Create the writer
    w = GeomWriter(
        p,
        lock=Lock(ctx=get_context()),
    )

    # Assert some simple stuff
    assert isinstance(w.lock, Lock)
    assert isinstance(w.buffer, GeomIO)

    # Clear the data
    w.close()


def test_geom_writer_setup_layer(
    tmp_path: Path,
    exposure_geom_data: GeomIO,
):
    p = Path(tmp_path, "tmp.geojson")
    # Create the writer
    w = GeomWriter(
        p,
        buffer_size=2,  # two features
    )
    # Assert the current state
    assert w.buffer.layer is None

    # Setup the (buffer) layer
    w.setup(
        defn=exposure_geom_data.layer.defn,
        srs=exposure_geom_data.srs,
    )

    # Assert the state
    assert w.buffer.layer is not None
    assert "object_id" in w.buffer.layer.fields

    # Close the data
    w.close()


def test_geom_writer_setup_layer_with_fields(
    tmp_path: Path,
    exposure_geom_data: GeomIO,
):
    p = Path(tmp_path, "tmp.geojson")
    # Create the writer
    w = GeomWriter(
        p,
        buffer_size=2,  # two features
    )
    # Assert the current state
    assert w.buffer.layer is None
    assert len(exposure_geom_data.layer.fields) == 5

    # Setup the (buffer) layer
    w.setup(
        defn=exposure_geom_data.layer.defn,
        srs=exposure_geom_data.srs,
        extra_fields={"foo": 0},
    )

    # Assert the state
    assert w.buffer.layer is not None
    assert "object_id" in w.buffer.layer.fields
    assert len(w.buffer.layer.fields) == 6
    assert "foo" in w.buffer.layer.fields

    # Close the data
    w.close()


def test_geom_writer_add(
    tmp_path: Path,
    exposure_geom_data: GeomIO,
):
    p = Path(tmp_path, "tmp.geojson")
    # Create the writer
    w = GeomWriter(
        p,
        buffer_size=2,  # two features
    )
    # Create the layer like dummy
    w.buffer.create_layer(
        srs=exposure_geom_data.srs,
        geom_type=exposure_geom_data.layer.geom_type,
    )
    w.buffer.layer.set_from_defn(defn=exposure_geom_data.layer.defn)
    w.defn = exposure_geom_data.layer.defn

    # Create a feature that can be written directly
    ft = ogr.Feature(w.buffer.layer.defn)
    ft.SetFrom(exposure_geom_data.layer[0])

    # Set directly
    w.add_feature(ft)
    # Assert that it is in the buffer
    assert w.buffer.layer.size == 1


def test_geom_writer_add_write(
    tmp_path: Path,
    exposure_geom_data: GeomIO,
):
    p = Path(tmp_path, "tmp.geojson")
    # Create the writer
    w = GeomWriter(
        p,
        buffer_size=2,  # two features
    )
    # Create the layer like dummy
    w.buffer.create_layer(
        srs=exposure_geom_data.srs,
        geom_type=exposure_geom_data.layer.geom_type,
    )
    w.buffer.layer.set_from_defn(defn=exposure_geom_data.layer.defn)
    w.defn = exposure_geom_data.layer.defn

    # Create a feature that can be written directly
    ft = ogr.Feature(w.buffer.layer.defn)
    ft.SetFrom(exposure_geom_data.layer[0])

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


def test_geom_writer_add_with_map(
    tmp_path: Path,
    exposure_geom_data: GeomIO,
):
    p = Path(tmp_path, "tmp.geojson")
    # Create the writer
    w = GeomWriter(
        p,
        buffer_size=2,  # two features
    )
    # Create the layer like dummy
    w.buffer.create_layer(
        srs=exposure_geom_data.srs,
        geom_type=exposure_geom_data.layer.geom_type,
    )
    w.buffer.layer.set_from_defn(defn=exposure_geom_data.layer.defn)
    w.defn = exposure_geom_data.layer.defn

    # Assert the size of the buffer
    assert w.buffer.layer.size == 0

    w.add_feature_with_map(exposure_geom_data.layer[0], fmap={})
    # Assert size of the buffer
    assert w.buffer.layer.size == 1

    w.add_feature_with_map(exposure_geom_data.layer[1], fmap={})
    # Assert size of the buffer
    assert w.buffer.layer.size == 2
    w.add_feature_with_map(exposure_geom_data.layer[2], fmap={})
    # Assert size of the buffer after dumping
    assert w.buffer.layer.size == 1

    # Close the data
    w.close()
