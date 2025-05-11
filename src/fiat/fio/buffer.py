"""Buffered writers."""

import os
from io import BytesIO, FileIO
from multiprocessing.synchronize import Lock
from pathlib import Path
from typing import Any

from osgeo import ogr, osr

from fiat.fio.fopen import open_geom
from fiat.fio.misc import merge_geom_layers
from fiat.util import (
    NEWLINE_CHAR,
    DummyLock,
)

__all__ = ["BufferedGeomWriter", "BufferedTextWriter"]


class BufferedGeomWriter:
    """Write geometries from a buffer.

    Parameters
    ----------
    file : str | Path
        Path to the file.
    srs : osr.SpatialReference
        The spatial reference system of the file (and the buffer).
    layer_defn : ogr.FeatureDefn, optional
        The definition of the layer, by default None
    buffer_size : int, optional
        The size of the buffer, by default 100000
    """

    def __init__(
        self,
        file: str | Path,
        srs: osr.SpatialReference,
        layer_defn: ogr.FeatureDefn = None,
        buffer_size: int = 100000,  # geometries
        lock: Lock = None,
    ):
        # Ensure pathlib.Path
        file = Path(file)
        self.file = file

        # Set the lock
        self.lock = lock
        if lock is None:
            self.lock = DummyLock()

        # Set for unique layer id's
        self.pid = os.getpid()

        # Set for later use
        self.srs = srs
        self.flds = {}
        self.n = 1

        if layer_defn is None:
            with open_geom(self.file, mode="r") as _r:
                layer_defn = _r.layer.defn
            _r = None
        self.layer_defn = layer_defn

        # Create the buffer
        self.buffer = open_geom(f"/vsimem/{file.stem}.gpkg", mode="w")
        self.buffer.create_layer(
            srs,
            layer_defn.GetGeomType(),
        )
        self.buffer.layer.set_from_defn(
            layer_defn,
        )
        # Set some check vars
        # TODO: do this based om memory foodprint
        # Needs some reseach into ogr's memory tracking
        self.max_size = buffer_size
        self.size = 0

    def __del__(self):
        self.buffer = None
        self.layer_defn = None

    def __reduce__(self) -> str | tuple[Any, ...]:
        pass

    def _reset_buffer(self):
        # Delete
        self.buffer.delete()

        # Re-create
        self.buffer.create_layer(
            self.srs,
            self.layer_defn.GetGeomType(),
        )
        self.buffer.layer.set_from_defn(
            self.layer_defn,
        )
        self.create_fields(self.flds)

        # Reset current size
        self.size = 0

    def close(self):
        """Close the buffer."""
        # Flush on last time
        self.to_drive()
        self.buffer.delete(all=True)
        self.buffer.close()

    def add_feature(
        self,
        ft: ogr.Feature,
    ):
        """Add a feature to the buffer.

        Parameters
        ----------
        ft : ogr.Feature
            The feature.
        """
        if self.size + 1 > self.max_size:
            self.to_drive()
        self.buffer.layer.add_feature(ft)

        self.size += 1

    def add_feature_with_map(
        self,
        ft: ogr.Feature,
        fmap: dict,
    ):
        """Add a feature to the buffer with additional field info.

        Parameters
        ----------
        ft : ogr.Feature
            The feature.
        fmap : dict
            Additional field information, the keys must align with \
the fields in the buffer.
        """
        if self.size + 1 > self.max_size:
            self.to_drive()
        self.buffer.layer.add_feature_with_map(
            ft,
            fmap=fmap,
        )

        self.size += 1

    def create_fields(
        self,
        flds: zip,
    ):
        """Create new fields in the buffer dataset."""
        _new = dict(flds)
        self.flds.update(_new)

        self.buffer.layer.create_fields(
            _new,
        )

    def to_drive(self):
        """Dump the buffer to the drive."""
        # Block while writing to the drive
        # self.buffer.close()
        self.lock.acquire()
        print("dumping")
        merge_geom_layers(
            self.file.as_posix(),
            f"/vsimem/{self.file.stem}.gpkg",
            out_layer_name=self.file.stem,
        )
        self.lock.release()

        # self.buffer = self.buffer.reopen(mode="w")
        self._reset_buffer()


class BufferedTextWriter(BytesIO):
    """Write text in chunks.

    Parameters
    ----------
    file : Path | str
        Path to the file.
    mode : str, optional
        Mode for opening the file. Byte-mode is mandatory, by default "wb"
    buffer_size : int, optional
        The size of the buffer, by default 524288 (which is 512 kb)
    """

    def __init__(
        self,
        file: Path | str,
        mode: str = "wb",
        buffer_size: int = 524288,  # 512 kB
        lock: Lock = None,
    ):
        # Set the lock
        self.lock = lock
        if lock is None:
            self.lock = DummyLock()

        BytesIO.__init__(self)

        # Set object specific stuff
        self.stream = FileIO(
            file=file,
            mode=mode,
        )
        self.max_size = buffer_size

    def close(self):
        """Close the writer and the buffer."""
        # Flush on last time
        self.to_drive()
        self.stream.close()

        # Close the buffer
        BytesIO.close(self)

    def to_drive(self):
        """Dump to buffer to the drive."""
        self.seek(0)

        # Push data to the file
        self.lock.acquire()
        self.stream.write(self.read())
        self.stream.flush()
        os.fsync(self.stream)
        self.lock.release()

        # Reset the buffer
        self.truncate(0)
        self.seek(0)

    def write(
        self,
        b: bytes,
    ):
        """Write bytes to the buffer.

        Parameters
        ----------
        b : bytes
            Bytes to write.
        """
        if self.tell() + len(b) > self.max_size:
            self.to_drive()
        BytesIO.write(self, b)

    def write_iterable(self, *args):
        """Write a multiple entries to the buffer."""
        by = b""
        for arg in args:
            by += ("," + "{}," * len(arg)).format(*arg).rstrip(",").encode()
        by = by.lstrip(b",")
        by += NEWLINE_CHAR.encode()
        self.write(by)
