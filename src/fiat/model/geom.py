"""Geom model of FIAT."""

import sys
import time
from itertools import chain
from multiprocessing.synchronize import Lock
from pathlib import Path
from typing import Any

from fiat.cfg import Configurations
from fiat.check import (
    check_geom_extent,
    check_input_data,
    check_internal_crs,
    check_vs_crs,
)
from fiat.fio import Dataset
from fiat.gis import geom
from fiat.job import execute_pool, generate_jobs
from fiat.log import spawn_logger
from fiat.model.base import BaseModel
from fiat.model.geom_util import generate_output_filepaths, get_exposure_meta
from fiat.model.geom_worker import initialize_pool, worker
from fiat.model.geom_writer import ensure_writable_filepath
from fiat.model.util import (
    create_1d_chunks,
    get_hazard_meta,
    get_run_meta,
    get_vulnerability_meta,
)
from fiat.open import open_geom
from fiat.struct import Container, Table
from fiat.struct.container import ExposureGeomData
from fiat.util import (
    AREA__METHOD,
    CENTROID,
    CHUNK,
    DAMAGE,
    EXPOSURE,
    EXPOSURE__META,
    EXPOSURE_GEOM,
    FILE,
    HAZARD,
    HAZARD__META,
    IMPACT__TYPES,
    MEAN,
    OUTPUT__PATH,
    OUTPUT_GEOM_FILE,
    OUTPUT_PATH,
    RUN__META,
    SETTINGS,
    VULNERABILITY,
    VULNERABILITY__META,
    ZONAL__METHOD,
    distribute_threads,
    generic_path_check,
    get_crs_repr,
)

logger = spawn_logger(__name__)


class GeomModel(BaseModel):
    """Geometry model.

    Needs the following settings in order to be run: \n
    - exposure.geom.file

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

        # Set/ declare some variables
        self.exposure: Container[ExposureGeomData] = Container()

        # Setup the geometry model
        self.read_exposure()

    def __del__(self):
        BaseModel.__del__(self)

    ## Read methods
    def read_exposure(
        self,
        path: Path | str = None,
        **kwargs: dict,
    ):
        """Read the exposure geometries.

        If no path is provided the method tries to
        infer it from the model configurations.

        Parameters
        ----------
        path : Path | str, optional
            A path to the file on the drive. Can contain a wildcard that take the form
            of an asterisk (*). Must be relative to the directory of the config.
            By default None.
        **kwargs : dict, optional
            Keyword arguments for reading. These are passed into [open_geom]\
(/api/fio/open_geom.qmd) after which into [GeomIO](/api/GeomIO.qmd)/
        """
        # Sort the settings
        # Hierarchy: 1) signature, 2) configurations
        settings: list[dict[str, Any]] | dict[str, Any] | None = None
        if path is not None:
            path = Path(self.cfg.path, path)
            settings = [{FILE: item} for item in path.parent.glob(path.name)]
        settings = settings or self.cfg.get(EXPOSURE_GEOM)
        if settings is None:
            return
        if not isinstance(settings, list):
            settings = [settings]  # Legacy

        # To set the config afterwards
        cfg = []

        # Move though the found paths
        for element in settings:
            path = element.get(FILE)
            if path is None:  # Can be as a result from the config
                continue

            # Check the path
            path = generic_path_check(path, root=self.cfg.path)

            # New config entry
            entry = {}
            # Get the settings
            kw = element.get(SETTINGS, {})
            kw.update(kwargs)  # For good measure

            logger.info(f"Reading exposure geometry ('{path.name}')")
            data = open_geom(path.as_posix(), **kw)
            ## checks
            logger.info("Executing exposure geometry checks...")

            # check the internal crs of the file
            check_internal_crs(
                data.layer.crs,
                path.name,
            )

            # check if file crs is the same as the model crs
            if not check_vs_crs(self.crs, data.layer.crs):
                logger.warning(
                    f"Spatial reference of '{path.name}' \
    ('{get_crs_repr(data.layer.crs)}') does not match \
    the model spatial reference ('{get_crs_repr(self.crs)}')"
                )
                logger.info(f"Reprojecting '{path.name}' to '{get_crs_repr(self.crs)}'")
                data = geom.reproject(data, self.crs.to_wkt())

            # Set the data
            self.exposure.set(
                ExposureGeomData(
                    area_method=element.get(AREA__METHOD, CENTROID),
                    data=data,
                    impact_types=element.get(IMPACT__TYPES, [DAMAGE]),
                    path=path,
                    zonal_method=element.get(ZONAL__METHOD, MEAN),
                )
            )
            # Set config entry
            entry[FILE] = path
            entry[SETTINGS] = kw
            cfg.append(entry)

        # Set the config back
        self.cfg.set(EXPOSURE_GEOM, cfg)

    ## Run model method
    def run(
        self,
    ):
        """Run the geometry model with provided settings.

        Generates output in the specified `output.path` directory.
        """
        logger.info("Running the model")
        # Quick check if all data is set
        check_input_data(
            [HAZARD, self.hazard, Dataset],
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

        # Create the output directory and files
        self.cfg.setup_output_dir()

        # Get the output filepaths
        output_paths = generate_output_filepaths(
            outfiles=self.cfg.get(OUTPUT_GEOM_FILE),
            infiles=[item.path for item in self.exposure],
            output_dir=self.cfg.output_dir,
        )

        # Get the thread loads
        logger.info("Distributing work load")
        threads = distribute_threads(
            size=[item.data.layer.size for item in self.exposure],
            threads=self.threads,
        )

        # Setup the lock
        lock = Lock(ctx=self.ctx)

        # Setup the jobs
        jobs_list = []
        for exposure, count, output_path in zip(self.exposure, threads, output_paths):
            # Check the extent
            check_geom_extent(
                exposure.data.layer.bounds,
                self.hazard.bounds,
            )
            # Get the exposure field meta
            exposure_meta = get_exposure_meta(
                exposure=exposure,
                run_meta=run_meta,
                hazard_meta=hazard_meta,
                method=self.method,
            )
            # Check the output file path
            ensure_writable_filepath(output_path)
            # Get the chunks based on the load distribution
            chunks = create_1d_chunks(exposure.data.layer.size, count)
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
            logger.info(f"Output generated in: '{self.cfg.get(OUTPUT_PATH)}'")
            logger.info("Model run is done!")
