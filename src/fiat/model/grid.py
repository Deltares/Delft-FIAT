"""The FIAT grid model."""

import sys
import time
from multiprocessing import Manager
from pathlib import Path

from fiat.check import (
    check_grid_exact,
    check_input_data,
    check_internal_srs,
    check_vs_srs,
)
from fiat.fio import GridIO, open_grid
from fiat.gis import grid
from fiat.job import execute_pool, generate_jobs
from fiat.log import spawn_logger
from fiat.model.base import BaseModel
from fiat.model.grid_util import get_exposure_meta
from fiat.model.util import (
    GRID_PREFER,
    get_hazard_meta,
    get_vulnerability_meta,
)
from fiat.model.worker_grid import worker
from fiat.struct import Table
from fiat.util import (
    EXPOSURE_GRID_FILE,
    create_2d_chunks,
    generic_path_check,
    get_srs_repr,
)

logger = spawn_logger(__name__)


class GridModel(BaseModel):
    """Grid model.

    Needs the following settings in order to be run: \n
    - exposure.grid.file
    - output.grid.file

    Parameters
    ----------
    cfg : Configurations
        Configurations object containing the settings.
    """

    def __init__(
        self,
        cfg: object,
    ):
        super().__init__(cfg)

        # Declare
        self.exposure: GridIO | None = None
        self.equal = True

        # Setup the model
        self.read_exposure()

    def __del__(self):
        BaseModel.__del__(self)

    def create_equal_grids(self):
        """Make the hazard and exposure grid equal spatially if necessary."""
        if self.equal:
            return

        # Get which way is preferred to reproject
        prefer = self.cfg.get("model.grid.prefer", "exposure")
        if prefer not in ["hazard", "exposure"]:
            raise ValueError(
                f"Preference value {prefer} not known. Chose from \
'hazard' or 'exposure'."
            )
        prefer_bool = prefer == "exposure"

        # Setup the data sets
        data = self.exposure
        data_warp = self.hazard
        if not prefer_bool:
            data = self.hazard
            data_warp = self.exposure

        # Reproject the data
        logger.info(
            f"Reprojecting {GRID_PREFER[not prefer_bool]} \
data to {prefer} data"
        )
        data_warped = grid.reproject(
            data_warp,
            get_srs_repr(data.srs),
            data.geotransform,
            *data.shape_xy,
        )

        # Set the output
        if prefer_bool:
            self.hazard = data_warped
            self.cfg.set("hazard.file", data_warped.path)
        else:
            self.exposure = data_warped
            self.cfg.set("exposure.grid.file", data_warped.path)

    def read_exposure(
        self,
        path: Path | str = None,
        **kwargs: dict,
    ):
        """Read the exposure grid.

        If no path is provided the method tries to
        infer it from the model configurations.

        Parameters
        ----------
        path : Path | str, optional
            Path to an exposure grid, by default None
        kwargs : dict, optional
            Keyword arguments for reading. These are passed into [open_grid]\
(/api/fio/open_grid.qmd) after which into [GridSouce](/api/GridIO.qmd)/
        """
        # Sort the pathing
        # Hierarchy: 1) signature, 2) configurations
        path = path or self.cfg.get(EXPOSURE_GRID_FILE)
        if path is None:
            return
        path = generic_path_check(path, root=self.cfg.path)
        logger.info(f"Reading exposure grid ('{path.name}')")

        # Set the extra arguments from the settings file
        kw = {}
        kw.update(
            self.cfg.generate_kwargs("exposure.grid.settings"),
        )
        kw.update(
            self.cfg.generate_kwargs("model.grid.chunk"),
        )
        kw.update(kwargs)
        data = open_grid(path, **kw)
        ## checks
        logger.info("Executing exposure data checks...")

        # Check if there is a srs present
        check_internal_srs(
            data.srs,
            path.name,
        )

        if not check_vs_srs(self.srs, data.srs):
            logger.warning(
                f"Spatial reference of '{path.name}' \
('{get_srs_repr(data.srs)}') does not match the \
model spatial reference ('{get_srs_repr(self.srs)}')"
            )
            logger.info(f"Reprojecting '{path.name}' to '{get_srs_repr(self.srs)}'")
            _resalg = self.cfg.get("exposure.grid.resampling_method", 0)
            data = grid.reproject(data, self.srs.ExportToWkt(), _resalg)

        # Reset to ensure the entry is present
        self.cfg.set(EXPOSURE_GRID_FILE, path)
        ## When all is done, add it
        self.exposure = data

    def run(self):
        """Run the grid model with provided settings.

        Generates output in the specified `output.path` directory.
        """
        logger.info("Running the model")
        # Quick check if all data is set
        check_input_data(
            ["hazard", self.hazard, GridIO],
            ["vulnerability", self.vulnerability, Table],
            ["exposure", self.exposure, GridIO],
        )

        # Setup the basic metadata
        hazard_meta = get_hazard_meta(self.hazard, risk=self.risk, method=self.method)
        vulnerability_meta = get_vulnerability_meta(self.vulnerability)
        # Get the exposure meta
        exposure_meta = get_exposure_meta(
            self.exposure,
            hazard_meta=hazard_meta,
            vulnerability_meta=vulnerability_meta,
        )

        # Create the output directory and files
        self.cfg.setup_output_dir()

        # Check for equal hazard and exposure grids
        self.equal = check_grid_exact(self.hazard, self.exposure)
        self.create_equal_grids()

        # Setup the manager
        if self._mp_manager is None:
            self._mp_manager = Manager()
        self._queue = self._mp_manager.Queue(maxsize=10000)

        # Setup the jobs
        chunks = create_2d_chunks(self.hazard.shape_xy, parts=self.threads)
        jobs = generate_jobs(
            {
                "output_dir": self.cfg.get("output.path"),
                "hazard": self.hazard,
                "hazard_meta": hazard_meta,
                "vulnerability": self.vulnerability,
                "vulnerability_meta": vulnerability_meta,
                "exposure": self.exposure,
                "exposure_meta": exposure_meta,
                "chunk": list(chunks),
            }
        )

        # Execute the jobs in a multiprocessing pool
        # Wrap to prevent weird error propagation with the pipes
        try:
            _s = time.time()
            logger.info("Busy...")
            execute_pool(
                ctx=self._mp_ctx,
                func=worker,
                jobs=jobs,
                threads=self.threads,
            )
            _e = time.time() - _s
            logger.info(f"Elapsed time: {round(_e, 2)} seconds")

        except BaseException:
            exc_info = sys.exc_info()
            msg = ",".join([str(item) for item in exc_info[1].args])
            logger.error(msg)
            exc_info = None

        else:
            logger.info(f"Output generated in: '{self.cfg.get('output.path')}'")
            logger.info("Model run is done!")

        # Shutdown the manager
        self._mp_manager.shutdown()
