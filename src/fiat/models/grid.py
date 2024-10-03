"""The FIAT grid model."""

import time

from fiat.check import (
    check_exp_grid_dmfs,
    check_grid_exact,
)
from fiat.gis import grid
from fiat.gis.crs import get_srs_repr
from fiat.io import open_grid
from fiat.log import spawn_logger
from fiat.models import worker_grid
from fiat.models.base import BaseModel
from fiat.models.util import GRID_PREFER, execute_pool, generate_jobs

logger = spawn_logger("fiat.model.grid")


class GridModel(BaseModel):
    """Grid model.

    Needs the following settings in order to be run: \n
    - exposure.grid.file
    - output.grid.file

    Parameters
    ----------
    cfg : ConfigReader
        ConfigReader object containing the settings.
    """

    def __init__(
        self,
        cfg: object,
    ):
        super().__init__(cfg)

        # Declare
        self.equal = True

        # Setup the model
        self.read_exposure_grid()
        self.create_equal_grids()

    def __del__(self):
        BaseModel.__del__(self)

    def _setup_output_files(self):
        pass

    def create_equal_grids(self):
        """Make the hazard and exposure grid equal spatially if necessary."""
        if self.equal:
            return

        # Get which way is preferred to reproject
        prefer = self.cfg.get("global.grid.prefer", "exposure")
        if prefer not in ["hazard", "exposure"]:
            raise ValueError(
                f"Preference value {prefer} not known. Chose from \
'hazard' or 'exposure'."
            )
        prefer_bool = prefer == "exposure"

        # Setup the data sets
        data = self.exposure_grid
        data_warp = self.hazard_grid
        if not prefer_bool:
            data = (self.hazard_grid,)
            data_warp = self.exposure_grid

        # Reproject the data
        logger.info(
            f"Reprojecting {GRID_PREFER[not prefer_bool]} \
data to {prefer} data"
        )
        data_warped = grid.reproject(
            data_warp,
            get_srs_repr(data.get_srs()),
            data.get_geotransform(),
            *data.shape_xy,
        )

        # Set the output
        if prefer_bool:
            self.hazard_grid = data_warped
            self.cfg.set("hazard.file", data_warped.path)
        else:
            self.exposure_grid = data_warped
            self.cfg.set("exposure.grid.file", data_warped.path)

    def read_exposure_grid(self):
        """Read the exposure grid."""
        file = self.cfg.get("exposure.grid.file")
        logger.info(f"Reading exposure grid ('{file.name}')")
        # Set the extra arguments from the settings file
        kw = {}
        kw.update(
            self.cfg.generate_kwargs("exposure.grid.settings"),
        )
        kw.update(
            self.cfg.generate_kwargs("global.grid.chunk"),
        )
        data = open_grid(file, **kw)
        ## checks
        logger.info("Executing exposure data checks...")
        # Check exact overlay of exposure and hazard
        self.equal = check_grid_exact(self.hazard_grid, data)
        # Check if all damage functions are correct
        check_exp_grid_dmfs(
            data,
            self.vulnerability_data.columns,
        )

        self.exposure_grid = data

    def resolve(self):
        """Create EAD output from the outputs of different return periods.

        This is done but reading, loading and iterating over the those files.
        In contrary to the geometry model, this does not concern temporary data.

        - This method might become private.
        """
        if self.cfg.get("hazard.risk"):
            logger.info("Setting up risk calculations..")

            # Time the function
            _s = time.time()
            worker_grid.worker_ead(
                self.cfg,
                self.exposure_grid.chunk,
            )
            _e = time.time() - _s
            logger.info(f"Risk calculation time: {round(_e, 2)} seconds")

    def run(self):
        """Run the grid model with provided settings.

        Generates output in the specified `output.path` directory.
        """
        _nms = self.cfg.get("hazard.band_names")
        # Setup the jobs
        jobs = generate_jobs(
            {
                "cfg": self.cfg,
                "haz": self.hazard_grid,
                "idx": range(1, self.hazard_grid.size + 1),
                "vul": self.vulnerability_data,
                "exp": self.exposure_grid,
            }
        )

        # Execute the jobs
        _s = time.time()
        logger.info("Busy...")
        pcount = min(self.threads, self.hazard_grid.size)
        execute_pool(
            ctx=self._mp_ctx,
            func=worker_grid.worker,
            jobs=jobs,
            threads=pcount,
        )

        # Last logging messages
        _e = time.time() - _s
        logger.info(f"Calculations time: {round(_e, 2)} seconds")
        self.resolve()
        logger.info(f"Output generated in: '{self.cfg.get('output.path')}'")
        logger.info("Grid calculation are done!")
