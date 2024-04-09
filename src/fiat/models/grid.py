"""The FIAT grid model."""

import time

from fiat.check import (
    check_exp_grid_dmfs,
    check_grid_exact,
)
from fiat.io import open_grid
from fiat.log import spawn_logger
from fiat.models.base import BaseModel
from fiat.models.util import execute_pool, generate_jobs
from fiat.models.worker import grid_worker_exact, grid_worker_risk

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

        self.read_exposure_grid()

    def __del__(self):
        BaseModel.__del__(self)

    def _clean_up(self):
        pass

    def read_exposure_grid(self):
        """_summary_."""
        file = self.cfg.get("exposure.grid.file")
        logger.info(f"Reading exposure grid ('{file.name}')")
        # Set the extra arguments from the settings file
        kw = {}
        kw.update(
            self.cfg.generate_kwargs("exposure.grid.settings"),
        )
        kw.update(
            self.cfg.generate_kwargs("global.grid"),
        )
        data = open_grid(file, **kw)
        ## checks
        logger.info("Executing exposure data checks...")
        # Check exact overlay of exposure and hazard
        check_grid_exact(self.hazard_grid, data)
        # Check if all damage functions are correct
        check_exp_grid_dmfs(
            data,
            self.vulnerability_data.columns,
        )

        self.exposure_grid = data

    def _set_num_threads(self):
        pass

    def _setup_output_files(self):
        pass

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
            grid_worker_risk(
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

        logger.info(f"Using number of threads: {self.nthreads}")

        # Execute the jobs
        _s = time.time()
        logger.info("Busy...")
        pcount = min(self.max_threads, self.hazard_grid.size)
        execute_pool(
            ctx=self._mp_ctx,
            func=grid_worker_exact,
            jobs=jobs,
            threads=pcount,
        )

        # Last logging messages
        _e = time.time() - _s
        logger.info(f"Calculations time: {round(_e, 2)} seconds")
        self.resolve()
        logger.info(f"Output generated in: '{self.cfg['output.path']}'")
        logger.info("Grid calculation are done!")
