"""Geom model of FIAT."""

import os
import sys
import time
from itertools import chain
from multiprocessing import Manager
from pathlib import Path

from osgeo_utils.ogrmerge import ogrmerge

from fiat.cfg import Configurations
from fiat.check import (
    check_geom_extent,
    check_internal_srs,
    check_vs_srs,
)
from fiat.fio import (
    open_geom,
)
from fiat.gis import geom
from fiat.job import execute_pool, generate_jobs
from fiat.log import setup_mp_log, spawn_logger
from fiat.models.base import BaseModel
from fiat.models.geom_util import get_exposure_meta
from fiat.models.worker_geom import worker
from fiat.struct import Container
from fiat.util import (
    EXPOSURE_GEOM_FILE,
    EXPOSURE_GEOM_SETTINGS,
    create_1d_chunks,
    distribute_threads,
    generic_path_check,
    get_srs_repr,
)

logger = spawn_logger("fiat.model.geom")


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
        self.exposure: Container = Container()
        self.exposure_types: list[str] = self.cfg.get("exposure.types", ["damage"])

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
            paths = list(self.cfg.path.glob(path))
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

            # check if it falls within the extent of the hazard map
            check_geom_extent(
                data.layer.bounds,
                self.hazard.bounds,
            )

            # Set the data
            self.exposure.set(data)
            # Set config entry
            entry["file"] = path
            entry["settings"] = kw
            cfg.append(entry)

        # Set the config back
        self.cfg.set("exposure.geom", cfg)

    ## Run model method
    def run(
        self,
    ):
        """Run the geometry model with provided settings.

        Generates output in the specified `output.path` directory.
        """
        # Setup the manager
        if self._mp_manager is None:
            self._mp_manager = Manager()
        self._queue = self._mp_manager.Queue(maxsize=10000)

        # Get the thread loads
        threads = distribute_threads(
            size=[item.layer.size for item in self.exposure],
            threads=self.threads,
        )

        # Create the output directory and files
        self.cfg.setup_output_dir()

        # Setup the mp logger for missing stuff
        _receiver = setup_mp_log(
            self._queue, "missing", level=2, dst=self.cfg.get("output.path")
        )
        logger.info("Starting the calculations")

        # Start the receiver (which is in a seperate thread)
        _receiver.start()

        # Setup the jobs
        jobs_list = []
        for exposure, count in zip(self.exposure, threads):
            # Get the exposure field meta
            meta = get_exposure_meta(
                exposure.layer._columns,
                module=self.module,
                exposure_types=self.exposure_types,
                band_names=self.cfg.get("hazard.band_names"),
                risk=self.risk,
            )
            # Get the chunks based on the load distribution
            chunks = create_1d_chunks(exposure.layer.size, count)
            # Second setup the lock
            lock = None
            if self.threads != 1:
                lock = self._mp_manager.Lock()
            # Generate the jobs
            jobs = generate_jobs(
                {
                    "cfg": self.cfg,
                    "risk": self.risk,
                    "haz": self.hazard,
                    "vul": self.vulnerability,
                    "exp": exposure,
                    "meta": meta,
                    "chunk": chunks,
                    "queue": self._queue,
                    "lock": lock,
                },
                # tied=["exp_data", "exp_geom", "idx"],
            )
            jobs_list.append(jobs)

        # Execute the jobs in a multiprocessing pool
        # Wrap to prevent weird error propagation with the pipes
        try:
            _s = time.time()
            logger.info("Busy...")
            execute_pool(
                ctx=self._mp_ctx,
                func=worker,
                jobs=chain(*jobs_list),
                threads=self.threads,
            )
            _e = time.time() - _s

            ogrmerge(
                src_datasets=[
                    item.as_posix()
                    for item in Path(self.cfg.get("output.path")).glob("spatial_*.gpkg")
                ],
                dst_filename=Path(self.cfg.get("output.path"), "spatial.gpkg"),
                driver_name="GPKG",
                append=True,
                overwrite_ds=True,
                single_layer=True,
                layer_name_template="spatial",
            )

            logger.info(f"Calculations time: {round(_e, 2)} seconds")

        except BaseException:
            exc_info = sys.exc_info()
            msg = ",".join([str(item) for item in exc_info[1].args])
            logger.error(msg)
            exc_info = None

        else:
            logger.info(f"Output generated in: '{self.cfg.get('output.path')}'")
            logger.info("Geom calculation are done!")

        _receiver.close()
        _receiver.close_handlers()
        if _receiver.count > 0:
            logger.warning(
                f"Some objects had missing data. For more info: \
'missing.log' in '{self.cfg.get('output.path')}'"
            )
        else:
            os.unlink(
                Path(self.cfg.get("output.path"), "missing.log"),
            )

        # Shutdown the manager
        self._mp_manager.shutdown()
