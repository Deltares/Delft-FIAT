from pathlib import Path

import pytest
from osgeo import ogr, osr

from fiat.error import DriverNotFoundError
from fiat.fio.geom import GeomIO
from fiat.struct import GeomLayer
from fiat.util import get_srs_repr


def test_geomio_read_only(exposure_geom_path: Path):
    # Open a Dataset
    gio = GeomIO(exposure_geom_path)

    # Assert some simple stuff
    assert gio.mode == 0
    assert get_srs_repr(gio.srs) == "EPSG:4326"
    assert isinstance(gio.layer, GeomLayer)


def test_geomio_read_errors(tmp_path: Path):
    # Read a file extension that is not accepted
    with pytest.raises(
        DriverNotFoundError,
        match="Geometry data -> \
Extension of file: tmp.unknown not recoqnized",
    ):
        _ = GeomIO(Path(tmp_path, "tmp.unknown"))
    pass

    # Read something that does not exist
    p = Path(tmp_path, "tmp.geojson")
    with pytest.raises(OSError, match=f"Cannot create {p.as_posix()} in 'read' mode."):
        _ = GeomIO(p)


def test_geomio_mode_errors(exposure_geom_path: Path):
    gio = GeomIO(exposure_geom_path)
    # Create e.g. a layer in read only mode
    with pytest.raises(ValueError, match="Invalid operation on a read-only file"):
        gio.create_layer(None, None)  # Doesn't matter that the args are bullshit

    # Close the dataset
    gio.close()

    with pytest.raises(ValueError, match="Invalid operation on a closed file"):
        _ = gio.layer


def test_geomio_write(tmp_path: Path, srs: osr.SpatialReference):
    p = Path(tmp_path, "tmp.geojson")
    # Open the dataset
    gio = GeomIO(p, mode="w")

    # Assert some simple stuff
    assert gio.mode == 1
    # It will already have create a data source
    assert gio.src is not None
    assert gio.layer is None  # But no layer present

    # Create a layer
    gio.create_layer(srs, geom_type=1)  # Point
    # Assert there is a layer
    assert gio.layer is not None
    assert ogr.GeometryTypeToName(gio.layer.geom_type) == "Point"


def test_geomio_write_append(exposure_geom_tmp_path: Path):
    # Open the dataset
    gio = GeomIO(exposure_geom_tmp_path, mode="w")

    # Assert some simple stuff
    assert gio.mode == 1
    # Even in write mode, it will already have a layer a its exists
    assert gio.layer is not None  # But no layer present
    assert gio.layer.size == 4


def test_geomio_write_overwrite(exposure_geom_tmp_path: Path):
    # Assert that the file exists
    assert exposure_geom_tmp_path.is_file()
    # Open the dataset
    gio = GeomIO(exposure_geom_tmp_path, mode="w", overwrite=True)

    # Assert some simple stuff
    assert gio.mode == 1
    # As the file is overwritten, the layer should be None
    assert gio.layer is None  # But no layer present


def test_geomio_write_delete(exposure_geom_tmp_path: Path):
    # Open the dataset
    gio = GeomIO(exposure_geom_tmp_path, mode="w")

    # Assert some simple stuff
    assert gio.src is not None
    assert gio.layer is not None
    assert gio.layer.size == 4

    # Delete the layer
    gio.delete(all=True)

    # Assert that its gone
    assert gio.src is None  # If src is None, layer cannot be requested
