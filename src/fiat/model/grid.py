"""The FIAT grid model."""

import sys
import time

from fiat.check import (
    check_input_data,
    check_internal_crs,
    check_vs_crs,
)
from fiat.driver import NetcdfReader
from fiat.driver.geotiff import create_geotiff_handle
from fiat.gis import grid
from fiat.job import execute_pool, generate_jobs
from fiat.log import spawn_logger
from fiat.model.base import BaseModel
from fiat.model.grid_util import equal_grid
from fiat.model.grid_worker import initialize_pool, worker
from fiat.model.meta import (
    get_exposure_grid_datasets,
    get_exposure_grid_meta,
    get_hazard_meta,
    get_method_types,
    get_run_meta,
    get_vulnerability_meta,
)
from fiat.model.util import apply_constants, create_2d_windows
from fiat.open import open_grid
from fiat.settings import GridSettings
from fiat.util import (
    EXPOSURE,
    EXPOSURE__META,
    HAZARD,
    HAZARD__META,
    RUN__META,
    VULNERABILITY,
    WINDOW,
    get_crs_repr,
)

logger = spawn_logger(__name__)


class GridModel(BaseModel):
    """Grid model.

    Parameters
    ----------
    settings : GridSettings
        Validated settings.
    """

    def __init__(
        self,
        settings: GridSettings,
    ):
        super().__init__(settings)

        # Declare
        self._exposure: NetcdfReader | None = None

        # Setup the model
        try:
            self._read_exposure()
        except BaseException:
            self.close()
            raise

    @property
    def exposure(self) -> NetcdfReader | None:
        """Return the exposure grid data."""
        return self._exposure

    def close(self) -> None:
        """Close the model data."""
        super().close()
        # Not yet declared when reading the base data fails
        exposure = getattr(self, "_exposure", None)
        if exposure is not None and not exposure.closed:
            exposure.close()

    def _read_exposure(self):
        """Read the exposure grid."""
        # Get the file and read kwargs
        file = self.settings.exposure.file
        kwargs = self.settings.exposure.settings.model_dump(exclude_none=True)

        logger.info(f"Reading exposure grid ('{file.name}')")
        data = open_grid(file, **kwargs)
        ## checks
        logger.info("Executing exposure data checks...")

        # Check if there is a crs present
        check_internal_crs(
            data.profile.crs,
            file.name,
        )

        if not check_vs_crs(self.crs, data.profile.crs):
            logger.warning(
                f"Spatial reference of '{file.name}' \
('{get_crs_repr(data.profile.crs)}') does not match the \
model spatial reference ('{get_crs_repr(self.crs)}')"
            )
            logger.info(f"Reprojecting '{file.name}' to '{get_crs_repr(self.crs)}'")
            _resalg = self.settings.exposure.resalg
            data = grid.reproject(data, self.crs.to_wkt(), _resalg)

        # Check the listed variables and add the constant layers
        apply_constants(data, self.settings.exposure.variables)

        ## When all is done, add it
        self._exposure = data

    def run(self):
        """Run the grid model with provided settings.

        Generates output in the specified `output.path` directory.
        """
        logger.info("Running the model")
        super().run()
        # Quick check if all cdata is set
        check_input_data(
            [HAZARD, self.hazard, NetcdfReader],
            [VULNERABILITY, self.vulnerability, NetcdfReader],
            [EXPOSURE, self.exposure, NetcdfReader],
        )

        # Check for equal hazard and exposure grids
        hazard, exposure = equal_grid(
            self.hazard,
            self.exposure,
            base=self.settings.grid.base,
        )
        # A reprojected dataset is a new reader, add the constant layers again
        if hazard is not self.hazard:
            apply_constants(hazard, self.settings.hazard.variables)
        if exposure is not self.exposure:
            apply_constants(exposure, self.settings.exposure.variables)
        self._hazard, self._exposure = hazard, exposure

        # Setup the basic metadata
        run_meta = get_run_meta(
            cell_size=self.hazard.get_attr_lazy("area_sqm") or 1.0,
            risk=self.risk,
        )
        # The datasets linked by the exposure variables
        vulnerability_meta = get_vulnerability_meta(
            self.vulnerability,
            self.settings.vulnerability.variables,
            names=get_exposure_grid_datasets(
                self.exposure,
                self.settings.exposure.variables,
            ),
        )
        hazard_meta = get_hazard_meta(
            self.hazard,
            self.settings.hazard.variables,
            risk=run_meta.risk,
            method_types=get_method_types(vulnerability_meta),
        )

        # Get the exposure meta
        exposure_meta = get_exposure_grid_meta(
            self.exposure,
            self.settings.exposure.variables,
            run_meta=run_meta,
            hazard_meta=hazard_meta,
            vulnerability_meta=vulnerability_meta,
        )

        # The tile size is also the parallel write granularity. Default to a
        # bounded 512x512 tile (clamped to the grid) so each worker processes and
        # writes one tile at a time instead of materialising the whole raster;
        # override via ``model.grid.chunk``.
        ny, nx = self.exposure.profile.shape
        chunk = self.settings.grid.chunk or (min(512, ny), min(512, nx))

        # Create the output handle and open it for direct, parallel tile writes.
        handle = create_geotiff_handle(
            path=self.settings.output.file,
            variables=exposure_meta.new,
            ds_like=self.exposure,
            crs=self.crs,
            cog=False,
            tile=chunk,
        )
        lock = handle.start_parallel(self.ctx)
        desc = handle.sink_descriptor()

        # One job per tile-aligned window covering the whole grid.
        windows = list(create_2d_windows((ny, nx), (0, 0), chunk))

        # Setup the jobs
        jobs = generate_jobs(
            {
                RUN__META: run_meta,
                HAZARD: self.hazard,
                HAZARD__META: hazard_meta,
                EXPOSURE: self.exposure,
                EXPOSURE__META: exposure_meta,
                WINDOW: windows,
            },
        )

        # Execute the jobs in a multiprocessing pool; workers write tiles
        # directly to the shared output and return their tile index records.
        try:
            _s = time.time()
            logger.info("Busy...")
            records = execute_pool(
                ctx=self.ctx,
                func=worker,
                jobs=jobs,
                threads=self.threads,
                initializer=initialize_pool,
                initargs=(desc, lock),
            )
            handle.collect_records(records)
            _e = time.time() - _s
            logger.info(f"Elapsed time: {round(_e, 2)} seconds")

        except BaseException:
            exc_info = sys.exc_info()
            msg = ",".join([str(item) for item in exc_info[1].args])
            logger.error(msg)
            exc_info = None

        else:
            logger.info(f"Output generated in: '{self.settings.output_dir}'")
            logger.info("Model run is done!")

        # Finalise and write the COG (overviews + header-first layout).
        handle.close()
