"""Writer for geom model."""

import os
from multiprocessing.synchronize import Lock
from pathlib import Path

from osgeo import gdal, ogr, osr

from fiat.fio.fopen import open_geom
from fiat.fio.geom import GeomIO
from fiat.util import DummyLock

__all__ = ["GeomWriter"]


class GeomWriter:
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

    ## State altering
    def close(self) -> None:
        """Close the buffer."""
        # Flush on last time
        if self.buffer.layer is not None:
            self.write(reset=False)
        self.buffer.delete(all=True)
        self.buffer.close()

    def reset_buffer(self):
        """Reset the buffer to an empty dataset/ layer."""
        if self.buffer.layer is None:
            return
        # Get the define
        defn = self.buffer.layer.defn
        srs = self.buffer.srs
        # Delete
        self.buffer.delete()

        # Re-create
        self.setup(defn, srs)

        # Reset current size
        self.size = 0
        defn = None
        srs = None

    ## I/O
    def write(self, reset: bool = True) -> None:
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

        if reset:
            self.reset_buffer()

    ## Mutating methods
    def add_feature(
        self,
        ft: ogr.Feature,
    ) -> None:
        """Add a feature to the buffer.

        Parameters
        ----------
        ft : ogr.Feature
            The feature.
        """
        if self.size + 1 > self.max_size:
            self.write()
        self.buffer.layer.add_feature(ft)
        # Added a new feature, so plus 1
        self.size += 1

    def add_feature_with_map(
        self,
        ft: ogr.Feature,
        fmap: zip,
    ) -> None:
        """Add a feature to the buffer with additional field info.

        Parameters
        ----------
        ft : ogr.Feature
            The feature.
        fmap : zip
            Additional field information, the keys must align with \
the fields in the buffer.
        """
        if self.size + 1 > self.max_size:
            self.write()
        self.buffer.layer.add_feature_with_map(
            ft,
            fmap=fmap,
        )
        # Added a new feature, so plus 1
        self.size += 1

    def setup(
        self,
        defn: ogr.FeatureDefn,
        srs: osr.SpatialReference,
        extra_fields: dict | zip | None = None,
    ) -> None:
        """Set up a layer for the buffer."""
        # Create the layer
        self.buffer.create_layer(srs, geom_type=defn.GetGeomType())
        self.buffer.layer.set_from_defn(defn)

        # Update the layer with new fields
        if extra_fields is not None:
            extra_fields = dict(extra_fields)  # Ensure typing
            self.buffer.layer.create_fields(extra_fields)
