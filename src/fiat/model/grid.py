"""The FIAT grid model."""

import time
from pathlib import Path

from fiat.check import (
    check_exp_grid_dmfs,
    check_grid_exact,
    check_internal_srs,
    check_vs_srs,
)
from fiat.fio import GridIO, open_grid
from fiat.gis import grid
from fiat.job import execute_pool, generate_jobs
from fiat.log import spawn_logger
from fiat.model import worker_grid
from fiat.model.base import BaseModel
from fiat.model.util import (
    GRID_PREFER,
)
from fiat.util import EXPOSURE_GRID_FILE, generic_path_check, get_srs_repr

logger = spawn_logger("fiat.model.grid")


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
        # Check if all damage functions are correct
        check_exp_grid_dmfs(
            [item.get_metadata_item("fn_damage") for item in self.exposure],
            self.vulnerability.columns,
        )
        # Check for equal hazard and exposure grids
        self.equal = check_grid_exact(self.hazard, self.exposure)
        self.create_equal_grids()

        # Setup the jobs
        chunks = []
        jobs = generate_jobs(
            {
                "output_dir": self.cfg.get("output.path"),
                "hazard": self.hazard,
                "vulnerability": self.vulnerability,
                "exposure": self.exposure,
                "chunk": chunks,
            }
        )

        # Execute the jobs
        _s = time.time()
        logger.info("Busy...")
        pcount = min(self.threads, self.hazard.size)
        execute_pool(
            ctx=self._mp_ctx,
            func=worker_grid.worker,
            jobs=jobs,
            threads=pcount,
        )

        # Last logging messages
        _e = time.time() - _s
        logger.info(f"Calculations time: {round(_e, 2)} seconds")
        logger.info(f"Output generated in: '{self.cfg.get('output.path')}'")
        logger.info("Grid calculation are done!")
