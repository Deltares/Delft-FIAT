"""Geom model of FIAT."""

import sys
import time
from itertools import chain
from multiprocessing.synchronize import Lock
from pathlib import Path

from fiat.cfg import Configurations
from fiat.check import (
    check_geom_extent,
    check_input_data,
    check_internal_srs,
    check_vs_srs,
)
from fiat.fio import (
    GeomIO,
    GridIO,
    open_geom,
)
from fiat.gis import geom
from fiat.job import execute_pool, generate_jobs
from fiat.log import spawn_logger
from fiat.model.base import BaseModel
from fiat.model.geom_util import generate_output_filepaths, get_exposure_meta
from fiat.model.geom_worker import initialize_pool, worker
from fiat.model.geom_writer import ensure_writable_filepath
from fiat.model.util import create_1d_chunks, get_hazard_meta, get_vulnerability_meta
from fiat.struct import Container, Table
from fiat.util import (
    CHUNK,
    EXPOSURE,
    EXPOSURE__META,
    EXPOSURE_GEOM,
    EXPOSURE_GEOM_FILE,
    EXPOSURE_GEOM_SETTINGS,
    EXPOSURE_TYPES,
    FILE,
    HAZARD,
    HAZARD__META,
    OUTPUT__PATH,
    OUTPUT_GEOM_NAME,
    SETTINGS,
    VULNERABILITY,
    VULNERABILITY__META,
    distribute_threads,
    generic_path_check,
    get_srs_repr,
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
        self.exposure: Container[GeomIO] = Container()
        self.exposure_types: list[str] = self.cfg.get(EXPOSURE_TYPES, ["damage"])

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
        # Sort the pathing
        # Hierarchy: 1) signature, 2) configurations
        paths = None
        if path is not None:
            path = Path(self.cfg.path, path)
            paths = list(path.parent.glob(path.name))
        paths = paths or self.cfg.get(EXPOSURE_GEOM_FILE)
        h = paths == self.cfg.get(EXPOSURE_GEOM_FILE)
        if not isinstance(paths, list):
            paths = [paths]  # Legacy purpose

        # To set the config afterwards
        cfg = []

        # Get the settings
        settings = self.cfg.get(EXPOSURE_GEOM_SETTINGS, {})
        if not isinstance(settings, list):
            settings = [settings]  # Legacy purpose
        if not h:
            settings = [kwargs] * len(paths)

        # Move though the found paths
        for idx, path in enumerate(paths):
            if path is None:  # Can be as a result from the config
                continue

            # Check the path
            path = generic_path_check(path, root=self.cfg.path)

            # New config entry
            entry = {}
            # Get the settings
            kw = settings[idx]
            kw.update(kwargs)  # For good measure

            logger.info(f"Reading exposure geometry ('{path.name}')")
            data = open_geom(path.as_posix(), **kw)
            ## checks
            logger.info("Executing exposure geometry checks...")

            # check the internal srs of the file
            check_internal_srs(
                data.layer.srs,
                path.name,
            )

            # check if file srs is the same as the model srs
            if not check_vs_srs(self.srs, data.layer.srs):
                logger.warning(
                    f"Spatial reference of '{path.name}' \
    ('{get_srs_repr(data.layer.srs)}') does not match \
    the model spatial reference ('{get_srs_repr(self.srs)}')"
                )
                logger.info(f"Reprojecting '{path.name}' to '{get_srs_repr(self.srs)}'")
                data = geom.reproject(data, self.srs.ExportToWkt())

            # Set the data
            self.exposure.set(data)
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
            [HAZARD, self.hazard, GridIO],
            [VULNERABILITY, self.vulnerability, Table],
            [EXPOSURE, self.exposure, GeomIO],
        )

        # Setup the basic metadata
        hazard_meta = get_hazard_meta(self.hazard, risk=self.risk, method=self.method)
        vulnerability_meta = get_vulnerability_meta(self.vulnerability)

        # Create the output directory and files
        self.cfg.setup_output_dir()

        # Get the output filepaths
        output_paths = generate_output_filepaths(
            outfiles=self.cfg.get(OUTPUT_GEOM_NAME),
            infiles=[item.path for item in self.exposure],
            output_dir=self.cfg.output_dir,
        )

        # Get the thread loads
        logger.info("Distributing work load")
        threads = distribute_threads(
            size=[item.layer.size for item in self.exposure],
            threads=self.threads,
        )

        # Setup the lock
        lock = Lock(ctx=self.ctx)

        # Setup the jobs
        jobs_list = []
        for exposure, count, output_path in zip(self.exposure, threads, output_paths):
            # Check the extent
            check_geom_extent(
                exposure.layer.bounds,
                self.hazard.bounds,
            )
            # Get the exposure field meta
            exposure_meta = get_exposure_meta(
                exposure=exposure,
                hazard_meta=hazard_meta,
                method=self.method,
                types=self.exposure_types,
            )
            # Check the output file path
            ensure_writable_filepath(output_path)
            # Get the chunks based on the load distribution
            chunks = create_1d_chunks(exposure.layer.size, count)
            # Generate the jobs
            jobs = generate_jobs(
                {
                    OUTPUT__PATH: output_path,
                    HAZARD: self.hazard,
                    HAZARD__META: hazard_meta,
                    VULNERABILITY__META: vulnerability_meta,
                    EXPOSURE: exposure,
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
            logger.info(f"Output generated in: '{self.cfg.get('output.path')}'")
            logger.info("Model run is done!")
