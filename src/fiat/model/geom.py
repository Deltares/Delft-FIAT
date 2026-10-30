"""Geom model of FIAT."""

import sys
import time
from itertools import chain
from multiprocessing.synchronize import Lock
from pathlib import Path

from fiat.check import (
    check_geom_extent,
    check_input_data,
    check_internal_crs,
    check_vs_crs,
)
from fiat.container import Container
from fiat.driver import NetcdfReader, Table, fgb
from fiat.gis import geom
from fiat.job import execute_pool, generate_jobs
from fiat.log import spawn_logger
from fiat.model.base import BaseModel
from fiat.model.geom_util import set_finalizing_params
from fiat.model.geom_worker import initialize_pool, worker
from fiat.model.meta import (
    ExposureGeomData,
    get_exposure_geom_meta,
    get_hazard_meta,
    get_run_meta,
    get_vulnerability_meta,
)
from fiat.model.util import create_1d_chunks
from fiat.open import open_geom
from fiat.settings import GeomSettings
from fiat.util import (
    CHUNK,
    EXPOSURE,
    EXPOSURE__META,
    HAZARD,
    HAZARD__META,
    OUTPUT__PATH,
    RUN__META,
    VULNERABILITY,
    VULNERABILITY__META,
    distribute_threads,
    get_crs_repr,
)

logger = spawn_logger(__name__)


def ensure_writable_filepath(filepath) -> None:
    """Remove any pre-existing output (and its FlatGeobuf body) at a path."""
    filepath = Path(filepath)
    if filepath.exists():
        filepath.unlink()
    body = Path(f"{filepath.as_posix()}.body")
    if body.exists():
        body.unlink()


class GeomModel(BaseModel):
    """Geometry model.

    Parameters
    ----------
    settings : GeomSettings
        Validated settings.
    """

    def __init__(
        self,
        settings: GeomSettings,
    ):
        super().__init__(settings)

        # Set/ declare some variables
        self._exposure: Container[ExposureGeomData] = Container()

        # Setup the geometry model
        self._read_exposure()

    ## Properties
    @property
    def exposure(self) -> Container:
        """Return the exposure data."""
        return self._exposure

    ## Read methods
    def _read_exposure(self):
        """Read the exposure geometries."""
        # Reset the exposure container so repeated calls are idempotent
        self._exposure = Container()

        # Move though the found paths
        for element in self.settings.exposure:
            # Get the file path and the reading kwargs
            file = element.file
            kwargs = element.settings.model_dump(exclude_none=True)

            # Read the file
            logger.info(f"Reading exposure geometry ('{file.name}')")
            data = open_geom(file, **kwargs)
            ## checks
            logger.info("Executing exposure geometry checks...")

            # check the internal crs of the file
            check_internal_crs(
                data.profile.crs,
                file.name,
            )

            # check if file crs is the same as the model crs
            if not check_vs_crs(self.crs, data.profile.crs):
                logger.warning(
                    f"Spatial reference of '{file.name}' \
    ('{get_crs_repr(data.profile.crs)}') does not match \
    the model spatial reference ('{get_crs_repr(self.crs)}')"
                )
                logger.info(f"Reprojecting '{file.name}' to '{get_crs_repr(self.crs)}'")
                data = geom.reproject(data, self.crs.to_wkt())

            # Set the data
            self._exposure.set(
                ExposureGeomData(
                    area_method=element.area_method,
                    data=data,
                    impact_types=element.impact_type,
                    path=file,
                    zonal_method=element.zonal_method,
                )
            )

    ## Run model method
    def run(
        self,
    ):
        """Run the geometry model with provided settings.

        Generates output in the specified `output.path` directory.
        """
        logger.info("Running the model")
        super().run()
        # Quick check if all data is set
        check_input_data(
            [HAZARD, self.hazard, NetcdfReader],
            [VULNERABILITY, self.vulnerability, Table],
            [EXPOSURE, self.exposure, ExposureGeomData],
        )

        # Setup the basic metadata
        run_meta = get_run_meta(
            risk=self.risk,
            method=self.method,
        )
        hazard_meta = get_hazard_meta(
            self.hazard,
            risk=self.risk,
            method_types=self.method.TYPES,
        )
        vulnerability_meta = get_vulnerability_meta(self.vulnerability)

        # Get the thread loads
        logger.info("Distributing work load")
        threads = distribute_threads(
            size=[item.data.profile.size for item in self.exposure],
            threads=self.threads,
        )

        # Setup the lock
        lock = Lock(ctx=self.ctx)

        # Setup the jobs
        jobs_list = []
        parameters = {}
        for exposure, count, output_path in zip(
            self.exposure,
            threads,
            [item.file for item in self.settings.output],
        ):
            # Check the extent
            check_geom_extent(
                exposure.data.profile.bounds,
                self.hazard.profile.bounds,
            )
            # Get the exposure field meta
            exposure_meta = get_exposure_geom_meta(
                exposure=exposure,
                run_meta=run_meta,
                hazard_meta=hazard_meta,
                method=self.method,
            )
            # Check the output file path
            ensure_writable_filepath(output_path)
            # Store the header parameters for the finalize pass
            set_finalizing_params(
                parameters,
                output_path=output_path,
                profile=exposure.data.profile,
                exposure_meta=exposure_meta,
            )
            # Get the chunks based on the load distribution
            chunks = create_1d_chunks(exposure.data.profile.size, count)
            # Generate the jobs
            jobs = generate_jobs(
                {
                    OUTPUT__PATH: output_path,
                    RUN__META: run_meta,
                    HAZARD: self.hazard,
                    HAZARD__META: hazard_meta,
                    VULNERABILITY__META: vulnerability_meta,
                    EXPOSURE: exposure.data,
                    EXPOSURE__META: exposure_meta,
                    CHUNK: chunks,
                },
            )
            jobs_list.append(jobs)

        # Execute the jobs in a multiprocessing pool
        # Wrap to prevent weird error propagation with the pipes
        try:
            _s = time.time()
            logger.info("Busy...")
            execute_pool(
                ctx=self.ctx,
                func=worker,
                jobs=chain(*jobs_list),
                threads=self.threads,
                initializer=initialize_pool,
                initargs=(lock, self.queue),
            )
            _e = time.time() - _s
            logger.info(f"Elapsed time: {round(_e, 2)} seconds")

        except BaseException:
            exc_info = sys.exc_info()
            msg = ",".join([str(item) for item in exc_info[1].args])
            logger.error(msg)
            exc_info = None

        else:
            # Finalize the output: build the packed R-tree and write indexed .fgb
            logger.info("Building spatial index and writing output...")
            fgb._finalize_outputs(self.queue, parameters)
            logger.info(f"Output generated in: '{self.settings.output_dir}'")
            logger.info("Model run is done!")
