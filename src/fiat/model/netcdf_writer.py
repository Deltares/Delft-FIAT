"""Writer for grid model."""

import weakref
from multiprocessing.connection import Connection
from multiprocessing.context import SpawnContext
from multiprocessing.queues import Queue
from multiprocessing.shared_memory import SharedMemory
from multiprocessing.synchronize import Lock
from pathlib import Path

import netCDF4 as nc4
import numpy as np
from osgeo import osr

from fiat.fio import GridIO
from fiat.model.grid_writer import GridItem
from fiat.thread import Receiver
from fiat.util import NODATA_VALUE


class Dataset:
    """_summary_.

    Parameters
    ----------
    file : Path | str
        _description_
    mode : str, optional
        _description_, by default "r"
    """

    def __init__(
        self,
        file: Path | str,
        mode: str = "r",
    ):
        # Load the source
        self.src = nc4.Dataset(filename=file, mode=mode)

        # Attributes
        self.gtf: tuple[float] | None = None
        self.ydim: nc4.Variable | None = None
        self.xdim: nc4.Variable | None = None
        self.srsdim: nc4.Variable | None = (None,)
        self.variables: dict[str, DataVariable] = {}

        if mode == "r":
            self._discover_variables()

    @property
    def origin(self) -> tuple[float]:
        """Return the origin of the grid."""
        xs, ys = self.xdim[:], self.ydim[:]
        dx, dy = self.res
        x0, y0 = xs[0] - dx / 2, ys[0] - dy / 2
        return x0, y0

    @property
    def res(self) -> tuple[float]:
        """Return the resolution of the data."""
        dxs, dys = np.diff(self.xdim[:]), np.diff(self.ydim[:])
        dx, dy = dxs.mean(), dys.mean()
        return dx, dy

    @property
    def size(self) -> int:
        """Return the number of data variables."""
        return len(self.variables)

    def _discover_spatial_dims(
        self,
    ):
        if self.xdim is not None and self.ydim is not None:
            return
        try:
            yvar = next(
                item in self.src.dimensions for item in ["y", "lat", "latitude"]
            )
            xvar = next(
                item in self.src.dimensions for item in ["x", "lon", "longitude"]
            )
            self.ydim = self.src.variables[xvar]
            self.xdim = self.src.variables[yvar]
        except StopIteration:
            raise ValueError("Couldn't derive the spatial dimensions")

    def _discover_reference_dim(self):
        try:
            var = next(item in self.src.dimensions for item in ["spatial_ref"])
            self.srsdim = self.src.variables[var]
        except StopIteration:
            ...

    def _discover_spatial_attr(self):
        self._discover_spatial_dims()
        origin = self.origin
        res = self.res
        self.gtf = (origin[0], res[0], 0.0, origin[1], 0.0, res[1])

    def _discover_variables(self):
        self._discover_reference_dim()
        srs_var = self.srsdim.name if self.srsdim is not None else None
        for var_name, var in self.src.variables.items():
            if var_name in self.src.dimensions or var_name == srs_var:
                continue
            if var_name not in self.variables:
                self.variables[var_name] = var

    def create_dim(
        self,
        dim: str,
        size: int,
    ):
        """_summary_."""
        self.src.createDimension(dimname=dim, size=size)

    def create_spatial_dims(
        self,
        lats: np.ndarray,
        lons: np.ndarray,
    ):
        """_summary_.

        Parameters
        ----------
        lats : np.ndarray
            _description_
        lons : np.ndarray
            _description_
        """
        self.src.createDimension(dimname="lat", size=len(lats))
        self.src.createDimension(dimname="lon", size=len(lons))
        self.ydim = self.src.createVariable(
            varname="lat",
            datatype="f4",
            dimensions=("lat",),
        )
        self.ydim[:] = np.sort(lats)[::-1]
        self.xdim = self.src.createVariable(
            varname="lon",
            datatype="f4",
            dimensions=("lon",),
        )
        self.xdim[:] = np.sort(lons)

    def create_spatial_variable(
        self,
        var: str,
        dtype: str = "f4",
        nodata: float = NODATA_VALUE,
        non_spatial_dims: tuple[str] = (),
    ):
        """_summary_.

        Parameters
        ----------
        var : str
            _description_
        extra_dims : tuple[str], optional
            _description_, by default ()
        """
        self._discover_spatial_dims()
        data = self.src.createVariable(
            varname=var,
            datatype=dtype,
            dimensions=(self.ydim.name, self.xdim.name),
            fill_value=nodata,
        )
        data.setncattr("grid_mapping", self.srsdim.name)
        self.variables[var] = DataVariable._create(var=data, ref=self.src)

    def set_spatial_ref(
        self,
        srs: osr.SpatialReference,
    ):
        """_summary_.

        Parameters
        ----------
        srs : osr.SpatialReference
            _description_
        """
        self.srsdim = self.src.createVariable("spatial_ref", datatype="i4")
        self.srsdim.setncatts({"x_dim": self.xdim.name, "y_dim": self.ydim.name})
        self.srsdim.setncatts(
            {
                "crs_wkt": srs.ExportToWkt(),
                "spatial_ref": srs.ExportToWkt(),
            }
        )
        self._discover_spatial_attr()
        gtf = [float(item) for item in self.gtf]
        self.srsdim.setncattr("GeoTransform", str(gtf).strip("[]").replace(",", ""))


class DataVariable:
    """Netcdf variable wrapper."""

    def __init__(
        self,
    ):
        # Object itself
        self._obj_ref: weakref.ReferenceType | None = None
        self._obj: nc4.Variable | None = None

        # Attributes
        self._nodata: float | None = None
        raise AttributeError("No constructer defined")

    ## Private methods
    def _cleanup(self, weak_ref):
        self._obj = None

    def _discover_attributes(self):
        self._nodata = self.__dict__.get("_FillValue")

    @classmethod
    def _create(
        cls,
        var: nc4.Variable,
        ref: nc4.Dataset,
    ):
        obj = DataVariable.__new__(cls)
        obj._obj_ref = weakref.ref(ref, obj._cleanup)
        obj._obj = var

        obj._discover_attributes()

        return obj

    ## Properties
    @property
    def name(self) -> str:
        """Return the name of the variable."""
        return self._obj.name

    @property
    def nodata(self) -> float | None:
        """Return the nodata value."""
        return self._nodata

    ## Mutating methods
    def mask_nodata(self):
        """_summary_."""
        ...

    def set(
        self,
        data: np.ndarray,
        origin: tuple[float],
    ):
        """Set data in the variable."""
        shape = data.shape
        self._obj[origin[1] : shape[0], origin[0] : shape[1]] = data


def create_netcdf_handle(
    path: Path | str,
    variables: list[str],
    ds_like: GridIO,
) -> Dataset:
    """_summary_.

    Parameters
    ----------
    path : Path | str
        _description_
    ds_like : GridIO
        _description_

    Returns
    -------
    Dataset
        _description_
    """
    # Open the dataset
    ds = Dataset(file=path, mode="w")
    # Get meta data from ds_like
    gtf = ds_like.geotransform
    ny, nx = ds_like.shape
    # Set the spatial dimensions
    ds.create_spatial_dims(
        lats=np.arange(gtf[3] + gtf[5] * 0.5, gtf[3] + gtf[5] * ny, gtf[5]),
        lons=np.arange(gtf[0] + gtf[1] * 0.5, gtf[0] + gtf[1] * nx, gtf[1]),
    )
    ds.set_spatial_ref(ds_like.srs)
    for var in variables:
        ds.create_spatial_variable(var=var)

    return ds


class NetcdfWriter(Receiver):
    """A writer for the grid model.

    Parameters
    ----------
    queue : Queue
        The queue through which to signal the parent process.
    handle : Dataset
        A handle to file to be written.
    ctx : SpawnContext
        The multiprocessing context currenly in use.
    """

    def __init__(
        self,
        handle: Dataset,
        queue: Queue,
        ctx: SpawnContext,
    ):
        # Inherit and set the handle
        super().__init__(queue=queue)
        self.handle = handle
        self.ctx = ctx

        # Components needed for the run
        self.locks: dict[str, Lock] = {}
        self.mem_locs: dict[str, SharedMemory] = {}
        self.mem_blocks: dict[str, np.ndarray] = {}
        self.piperecv: dict[str, Connection] = {}
        self.pipesend: dict[str, Connection] = {}

    ## I/O methods
    def _close(self):
        """Close method specific for this class."""
        # self.handle.close()
        # Close all memory blocks
        mem_ids = list(self.mem_locs.keys())
        for mem_id in mem_ids:
            _ = self.locks.pop(mem_id)
            _ = self.mem_blocks.pop(mem_id)
            mem_loc = self.mem_locs.pop(mem_id)
            mem_loc.close()
            mem_loc.unlink()
            pipe = self.piperecv.pop(mem_id)
            pipe.close()
            pipe = self.pipesend.pop(mem_id)
            pipe.close()

    def close(self):
        """Close the grid writer."""
        super().close()
        self._close()

    ## Setup method
    def setup_block(
        self,
        mem_id: str,
        shape: tuple[int],
    ):
        """Create a block of shared memory.

        This also creates other necessary components, which are:
        lock, numpy.ndarray, pipeline.

        Parameters
        ----------
        mem_ids : list[str]
            Identifiers of the memory blocks.
        shape : tuple[int]
            The shape of the memory block.
        """
        # Calculate the size of the mem blocks based on the shape of the block
        size = self.handle.size * shape[0] * shape[1] * 4  # 4 bytes for Float32
        # Loop through the id's to create the components
        self.locks[mem_id] = self.ctx.Lock()
        self.mem_locs[mem_id] = SharedMemory(
            name=mem_id,
            create=True,
            size=size,
        )
        self.mem_blocks[mem_id] = np.ndarray(
            shape=(self.handle.size, *shape),
            dtype=np.float32,
            buffer=self.mem_locs[mem_id].buf,
        )
        self.mem_blocks[mem_id][:] = np.nan
        self.piperecv[mem_id], self.pipesend[mem_id] = self.ctx.Pipe(duplex=False)

    ## Worker method
    def fn(
        self,
        record: GridItem,
    ) -> None:
        """Write data from a shared memory block."""
        # Get the id
        mem_id = record.mem_id
        w, h = record.shape

        # Acquire the lock
        self.locks[mem_id].acquire()
        # Get the block of memory in the form of a numpy array
        block = self.mem_blocks[mem_id]
        block[np.isnan(block)] = NODATA_VALUE
        # Write from the block
        for idx, band in enumerate(self.handle.variables.values()):
            band.set(
                block[idx, :h, :w],
                record.origin,
            )
        # Reset everything to nan
        block[:] = np.nan
        block = None

        # Flush the handle
        # self.handle.flush()

        # Release the lock back for the worker to use
        self.locks[mem_id].release()
        self.pipesend[mem_id].send(None)


if __name__ == "__main__":
    from fiat.fio import open_grid

    gs = open_grid(r"c:\temp\fiat_cases\majuro_v1\hazard.nc")
    gtf = gs.geotransform
    ny, nx = gs.shape
    ds = create_netcdf_handle("tmp/foo.nc", ["data"], gs)
    var = ds.variables["data"]
    var.set(gs[0]._obj.ReadAsArray(), origin=(0, 0))
    ds.src.close()
    gs.close()
    pass
