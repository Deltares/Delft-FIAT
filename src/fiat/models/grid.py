"""The FIAT grid model."""

import time
from concurrent.futures import ProcessPoolExecutor, wait
from multiprocessing import Process

from fiat.check import (
    check_exp_grid_dmfs,
    check_grid_exact,
)
from fiat.io import open_grid
from fiat.log import spawn_logger
from fiat.models.base import BaseModel
from fiat.models.util import grid_worker_exact, grid_worker_risk

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

        self._read_exposure_grid()

    def __del__(self):
        BaseModel.__del__(self)

    def _clean_up(self):
        pass

    def _read_exposure_grid(self):
        """_summary_."""
        file = self.cfg.get("exposure.grid.file")
        logger.info(f"Reading exposure grid ('{file.name}')")
        # Set the extra arguments from the settings file
        kw = {}
        kw.update(
            self.cfg.generate_kwargs("global.grid"),
        )
        kw.update(
            self.cfg.generate_kwargs("exposure.grid.settings"),
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

        if self.hazard_grid.count > 1:
            pcount = min(self.max_threads, self.hazard_grid.count)
            futures = []
            with ProcessPoolExecutor(max_workers=pcount) as Pool:
                _s = time.time()
                for idx in range(self.hazard_grid.count):
                    logger.info(
                        f"Submitting a job for the calculations \
in regards to band: '{_nms[idx]}'"
                    )
                    fs = Pool.submit(
                        grid_worker_exact,
                        self.cfg,
                        self.hazard_grid,
                        idx + 1,
                        self.vulnerability_data,
                        self.exposure_grid,
                    )
                    futures.append(fs)
            logger.info("Busy...")
            # Wait for the children to finish their calculations
            wait(futures)

        else:
            logger.info("Submitting a job for the calculations in a seperate process")
            _s = time.time()
            p = Process(
                target=grid_worker_exact,
                args=(
                    self.cfg,
                    self.hazard_grid,
                    1,
                    self.vulnerability_data,
                    self.exposure_grid,
                ),
            )
            p.start()
            logger.info("Busy...")
            p.join()
        _e = time.time() - _s
        logger.info(f"Calculations time: {round(_e, 2)} seconds")
        self.resolve()
        logger.info(f"Output generated in: '{self.cfg['output.path']}'")
        logger.info("Grid calculation are done!")
