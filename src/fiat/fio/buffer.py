"""Buffered writers."""

import os
from io import BytesIO, FileIO
from multiprocessing.synchronize import Lock
from pathlib import Path

from osgeo import gdal, ogr, osr

from fiat.fio.fopen import open_geom
from fiat.fio.geom import GeomIO
from fiat.util import (
    NEWLINE_CHAR,
    DummyLock,
)

__all__ = ["BufferedGeomWriter", "BufferedTextWriter"]


class BufferedGeomWriter:
    """Write geometries from a buffer.

    Parameters
    ----------
    file : Path | str
        Path to the file.
    buffer_size : int, optional
        The size of the buffer, by default 100000
    lock : Lock, optional
        A lock for multiprocessing, by default None
    """

    def __init__(
        self,
        file: Path | str,
        buffer_size: int = 100000,  # geometries
        lock: Lock = None,
    ):
        # Ensure pathlib.Path
        path = Path(file)
        self.path: Path = path

        # Set the lock
        self.lock: Lock | DummyLock = lock
        if lock is None:
            self.lock = DummyLock()

        # Set for unique layer id's
        self.pid: int = os.getpid()

        # Set for later use
        self.defn: ogr.FeatureDefn | None = None
        self.srs: osr.SpatialReference | None = None
        self.flds: dict[str, int] = {}
        self.n: int = 1

        # Create the buffer
        self.buffer: GeomIO = open_geom(f"/vsimem/{file.stem}.gpkg", mode="w")

        # Set some check vars
        # TODO: do this based om memory foodprint
        # Needs some reseach into ogr's exposed memory tracking
        self.max_size: int = buffer_size
        self.size: int = 0

    def __del__(self):
        self.buffer = None
        self.layer_defn = None
        self.srs = None

    ## State altering
    def close(self):
        """Close the buffer."""
        # Flush on last time
        self.write()
        self.buffer.delete(all=True)
        self.buffer.close()

    def reset_buffer(self):
        """Reset the buffer to an empty dataset/ layer."""
        # Delete
        self.buffer.delete(all=True)

        # Re-create
        self.buffer.create(self.buffer.path)
        self.setup_layer(self.defn, self.srs, self.flds)

        # Reset current size
        self.size = 0

    ## I/O
    def write(self):
        """Dump the buffer to the drive."""
        # Block while writing to the drive
        self.buffer.flush()
        # self.buffer.src.Close()

        # Lock and merge/ write
        self.lock.acquire()
        ds = gdal.VectorTranslate(
            self.path.as_posix(),
            self.buffer.path.as_posix(),
            format="GPKG",
            accessMode="append",
        )
        ds.Close()
        ds = None
        self.lock.release()

        # self.buffer = self.buffer.reopen(mode="w")
        self.reset_buffer()

    ## Mutating methods
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
            self.write()
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
            self.write()
        self.buffer.layer.add_feature_with_map(
            ft,
            fmap=fmap,
        )

        self.size += 1

    def setup_layer(
        self,
        defn: ogr.FeatureDefn,
        srs: osr.SpatialReference,
        flds: dict | zip,
    ):
        """Set up a layer for the buffer."""
        # Create the layer
        self.buffer.create_layer(srs, geom_type=defn.GetGeomType())
        self.buffer.layer.set_from_defn(defn)
        # Update the internals
        self.srs = srs
        self.defn = defn

        # Update the layer with new fields
        flds = dict(flds)  # Ensure typing
        self.flds.update(flds)  # Combine with existing
        self.buffer.layer.create_fields(flds)


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
