"""Writer for grid model."""

from dataclasses import dataclass
from multiprocessing.context import SpawnContext
from multiprocessing.queues import Queue
from multiprocessing.shared_memory import SharedMemory
from multiprocessing.synchronize import Lock
from pathlib import Path

import numpy as np
from osgeo import osr

from fiat.fio import GridIO, open_grid
from fiat.thread import Receiver
from fiat.util import NODATA_VALUE


def create_grid_handle(
    path: Path,
    shape: tuple[int],
    nb: int,
    srs: osr.SpatialReference,
    gtf: tuple[float | int],
) -> GridIO:
    """_summary_.

    Parameters
    ----------
    path : Path
        _description_
    exposure : GridIO
        _description_
    exposure_meta : ExposureGridMeta
        _description_
    """
    # Ensure typing
    path = Path(path)
    # If exists, unlink
    if path.exists():
        path.unlink()

    # Create a new data
    out = open_grid(path, mode="w")
    out.create(
        shape=shape,
        nb=nb,
        dtype=6,  # Float32
        options=["FORMAT=NC4", "COMPRESS=DEFLATE"],
    )
    out.set_source_srs(srs)
    out.geotransform = gtf
    for band in out.bands:
        band.nodata = NODATA_VALUE

    return out


@dataclass
class GridItem:
    """Small struct for signalling."""

    mem_id: str
    origin: tuple
    shape: tuple


class GridWriter(Receiver):
    """A writer for the grid model.

    Parameters
    ----------
    queue : Queue
        The queue through which to signal the parent process.
    handle : GridIO
        A handle to file to be written.
    """

    def __init__(
        self,
        queue: Queue,
        handle: GridIO,
    ):
        # Inherit and set the handle
        super().__init__(queue=queue)
        self.handle = handle

        # Components needed for the run
        self.locks: dict[str, Lock] = {}
        self.mem_locs: dict[str, SharedMemory] = {}
        self.mem_blocks: dict[str, np.ndarray] = {}

    ## I/O methods
    def _close(self):
        """Close method specific for this class."""
        self.handle.close()
        # Close all memory blocks
        mem_ids = list(self.mem_locs.keys())
        for mem_id in mem_ids:
            _ = self.locks.pop(mem_id)
            _ = self.mem_blocks.pop(mem_id)
            mem_loc = self.mem_locs.pop(mem_id)
            mem_loc.close()
            mem_loc.unlink()

    def close(self):
        """Close the grid writer."""
        super().close()
        self._close()

    ## Setup method
    def setup_components(
        self,
        mem_ids: list[str],
        ctx: SpawnContext,
        shape: tuple[int],
    ):
        """Create the necessary components for working with shared memory.

        Parameters
        ----------
        mem_ids : list[str]
            Identifiers of the memory blocks.
        ctx : SpawnContext
            The multiprocessing context currenly in use.
        shape : tuple[int]
            The shape of the memory block.
        """
        # Calculate the size of the mem blocks based on the shape of the block
        size = shape[0] * shape[1] * 4  # 4 bytes for Float32
        # Loop through the id's to create the components
        for mem_id in mem_ids:
            self.locks[mem_id] = ctx.Lock()
            self.mem_locs[mem_id] = SharedMemory(
                name=mem_id,
                create=True,
                size=size,
            )
            self.mem_blocks[mem_id] = np.ndarray(
                shape=shape,
                dtype=np.float32,
                buffer=self.mem_locs[mem_id].buf,
            )
            self.mem_blocks[mem_id][:] = np.nan

    ## Worker method
    def fn(
        self,
        record: GridItem,
    ) -> None:
        """Write data from a shared memory block."""
        # Get the id
        mem_id = record.mem_id

        # Acquire the lock
        self.locks[mem_id].acquire()
        # Get the block of memory in the form of a numpy array
        block = self.mem_blocks[mem_id]
        block[np.isnan(block)] = NODATA_VALUE
        # Write from the block
        for idx, band in enumerate(self.handle):
            band.write(
                block[idx, :, :],
            )
        # Reset everything to nan
        block[:] = np.nan
        block = None

        # Release the lock back for the worker to use
        self.locks[mem_id].release()
