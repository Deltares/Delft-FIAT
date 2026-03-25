"""The FIAT grid model."""

import sys
import time
from pathlib import Path

from fiat.cfg import Configurations
from fiat.check import (
    check_input_data,
    check_internal_srs,
    check_vs_srs,
)
from fiat.fio import GridIO, open_grid
from fiat.gis import grid
from fiat.job import execute_pool, generate_jobs
from fiat.log import spawn_logger
from fiat.model.base import BaseModel
from fiat.model.grid_util import equal_grid, get_exposure_meta
from fiat.model.grid_worker import initialize_pool, worker
from fiat.model.grid_writer import GridWriter, create_grid_handle
from fiat.model.util import (
    create_2d_chunks,
    get_hazard_meta,
    get_run_meta,
    get_vulnerability_meta,
)
from fiat.struct import Table
from fiat.util import (
    CHUNK,
    EXPOSURE,
    EXPOSURE__META,
    EXPOSURE_GRID_FILE,
    EXPOSURE_GRID_RESALG,
    EXPOSURE_GRID_SETTINGS,
    HAZARD,
    HAZARD__META,
    MODEL_GRID_CHUNK,
    MODEL_GRID_LEADING,
    OUTPUT_GRID_NAME,
    RUN__META,
    VULNERABILITY,
    VULNERABILITY__META,
    WINDOW,
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
        cfg: Configurations,
    ):
        super().__init__(cfg)

        # Declare
        self.exposure: GridIO | None = None

        # Setup the model
        self.read_exposure()

    def __del__(self):
        BaseModel.__del__(self)

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
            self.cfg.generate_kwargs(EXPOSURE_GRID_SETTINGS),
        )
        kw.update(
            self.cfg.generate_kwargs(MODEL_GRID_CHUNK),
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
            _resalg = self.cfg.get(EXPOSURE_GRID_RESALG, 0)
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
        # Quick check if all cdata is set
        check_input_data(
            [HAZARD, self.hazard, GridIO],
            [VULNERABILITY, self.vulnerability, Table],
            [EXPOSURE, self.exposure, GridIO],
        )

        # Setup the basic metadata
        run_meta = get_run_meta(self.cfg, risk=self.risk, method=self.method)
        hazard_meta = get_hazard_meta(
            self.hazard,
            risk=run_meta.risk,
            method_types=self.method.TYPES,
        )
        vulnerability_meta = get_vulnerability_meta(self.vulnerability)

        # Get the exposure meta
        exposure_meta = get_exposure_meta(
            self.exposure,
            run_meta=run_meta,
            hazard_meta=hazard_meta,
            vulnerability_meta=vulnerability_meta,
        )

        # Create the output directory and files
        self.cfg.setup_output_dir()

        # Check for equal hazard and exposure grids
        self.hazard, self.exposure = equal_grid(
            self.hazard,
            self.exposure,
            first=self.cfg.get(MODEL_GRID_LEADING, True),
        )

        # Get the output path
        output_name = self.cfg.get(OUTPUT_GRID_NAME) or self.exposure.path.name
        output_filepath = Path(self.cfg.output_dir, output_name)

        # Setup the queue and the writer
        self.queue = self.ctx.Queue(maxsize=1000)
        handle = create_grid_handle(
            path=output_filepath,
            shape=self.exposure.shape_xy,
            nb=exposure_meta.nb,
            srs=self.exposure.srs,
            gtf=self.exposure.geotransform,
        )
        writer = GridWriter(handle=handle, queue=self.queue, ctx=self.ctx)

        # Get the chunks and the window(s)
        chunks = list(create_2d_chunks(self.hazard.shape, parts=self.threads))
        window = self.cfg.get(MODEL_GRID_CHUNK, fallback=self.exposure.shape)
        mem_ids = [f"grid_worker{idx}" for idx, _ in enumerate(chunks)]
        for mem_id, chunk in zip(mem_ids, chunks):
            writer.setup_block(mem_id=mem_id, shape=window)
        writer.start()

        # Setup the jobs
        jobs = generate_jobs(
            {
                "mem_id": mem_ids,
                RUN__META: run_meta,
                HAZARD: self.hazard,
                HAZARD__META: hazard_meta,
                VULNERABILITY__META: vulnerability_meta,
                EXPOSURE: self.exposure,
                EXPOSURE__META: exposure_meta,
                CHUNK: chunks,
                WINDOW: [window],
            },
            tied=["mem_id", CHUNK],
        )

        # Execute the jobs in a multiprocessing pool
        # Wrap to prevent weird error propagation with the pipes
        try:
            _s = time.time()
            logger.info("Busy...")
            execute_pool(
                ctx=self.ctx,
                func=worker,
                jobs=jobs,
                threads=self.threads,
                initializer=initialize_pool,
                initargs=(self.queue, writer.piperecv),
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

        # Close the writer
        writer.close()
