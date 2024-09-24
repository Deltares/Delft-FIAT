"""Geom model of FIAT."""

import os
import time
from pathlib import Path

from fiat.cfg import ConfigReader
from fiat.check import (
    check_exp_columns,
    check_exp_derived_types,
    check_geom_extent,
    check_internal_srs,
    check_vs_srs,
)
from fiat.gis import geom, overlay
from fiat.gis.crs import get_srs_repr
from fiat.io import (
    open_geom,
)
from fiat.log import setup_mp_log, spawn_logger
from fiat.models import worker_csv
from fiat.models.base import BaseModel
from fiat.models.util import (
    GEOM_MIN_CHUNK,
    GEOM_MIN_WRITE_CHUNK,
    execute_pool,
    generate_jobs,
    geom_threads,
)
from fiat.util import create_1d_chunk, discover_exp_columns, generate_output_columns

logger = spawn_logger("fiat.model.geom")


class GeomModel(BaseModel):
    """Geometry model.

    Needs the following settings in order to be run: \n
    - exposure.csv.file
    - exposure.geom.file1
    - output.geom.file1

    Parameters
    ----------
    cfg : ConfigReader
        ConfigReader object containing the settings.
    """

    _method = {
        "area": overlay.clip,
        "centroid": overlay.pin,
    }

    def __init__(
        self,
        cfg: ConfigReader | dict,
    ):
        super().__init__(cfg)

        self._exposure_csv = self.cfg.get("exposure.use_csv", False)
        self.exposure_types = self.cfg.get("exposure.types", ["damage"])

        # Setup the geometry model
        self.read_exposure_geoms()
        self.check_exposure_types()
        self._set_chunking()
        self._set_num_threads()
        self._queue = self._mp_manager.Queue(maxsize=10000)

    def __del__(self):
        BaseModel.__del__(self)

    def _clean_up(self):
        """_summary_."""
        _p = self.cfg.get("output.tmp.path")
        for _f in _p.glob("*"):
            os.unlink(_f)
        os.rmdir(_p)

    def _set_chunking(self):
        """_summary_."""
        # Determine maximum geometry dataset size
        max_geom_size = max(
            [item.size for item in self.exposure_geoms.values()],
        )
        # Set calculations chunk size
        self.chunk = max_geom_size
        _chunk = self.cfg.get("global.geom.chunk")
        if _chunk is not None:
            self.chunk = max(GEOM_MIN_CHUNK, _chunk)

        # Set cache size for outgoing data
        _out_chunk = self.cfg.get("output.geom.settings.chunk")
        if _out_chunk is None:
            _out_chunk = GEOM_MIN_WRITE_CHUNK
        self.cfg.set("output.geom.settings.chunk", _out_chunk)

        # Determine amount of threads
        self.nchunk = max_geom_size // self.chunk
        if self.nchunk == 0:
            self.nchunk = 1
        # Constrain by max threads
        if self.max_threads < self.nchunk:
            logger.warning(
                f"Less threads ({self.max_threads}) available than \
calculated chunks ({self.nchunk})"
            )
            self.nchunk = self.max_threads

        # Set the 1D chunks
        self.chunks = create_1d_chunk(
            max_geom_size,
            self.nchunk,
        )

    def _set_num_threads(self):
        """_summary_."""
        self.nthreads = geom_threads(
            self.max_threads,
            self.hazard_grid.size,
            self.nchunk,
        )

    def _setup_output_files(self):
        """_summary_."""
        # Do the same for the geometry files
        for key in self.exposure_geoms.keys():
            _add = key[-1]
            # Define outgoing dataset
            out_geom = f"spatial{_add}.gpkg"
            if f"output.geom.name{_add}" in self.cfg:
                out_geom = self.cfg.get(f"output.geom.name{_add}")
            self.cfg.set(f"output.geom.name{_add}", out_geom)
            with open_geom(
                Path(self.cfg.get("output.path"), out_geom), mode="w", overwrite=True
            ) as _w:
                pass

    def check_exposure_types(self):
        """_summary_."""
        # Get the relevant column headers
        columns = self.exposure_geoms["file1"]._columns

        # Check the exposure column headers
        check_exp_columns(
            list(columns.keys()),
            specific_columns=getattr(self.module, "MANDATORY_COLUMNS"),
        )

        # Check the found columns
        types = {}
        for t in self.exposure_types:
            types[t] = {}
            found, found_idx, missing = discover_exp_columns(columns, type=t)
            check_exp_derived_types(t, found, missing)
            types[t] = found_idx

        self.cfg.set("exposure.types", types)

        ## Information for output
        extra = []
        if self.cfg.get("hazard.risk"):
            extra = ["ead"]
        new_cols, len1, total_idx = generate_output_columns(
            getattr(self.module, "NEW_COLUMNS"),
            types,
            extra=extra,
            suffix=self.cfg.get("hazard.band_names"),
        )
        self.cfg.set("output.new_columns", new_cols)
        self.cfg.set("output.csv.slen", len1)
        self.cfg.set("output.csv.total_idx", total_idx)

    def read_exposure_geoms(self):
        """_summary_."""
        _d = {}
        _found = [item for item in list(self.cfg) if "exposure.geom.file" in item]
        for file in _found:
            path = self.cfg.get(file)
            logger.info(
                f"Reading exposure geometry '{file.split('.')[-1]}' ('{path.name}')"
            )
            data = open_geom(str(path))
            ## checks
            logger.info("Executing exposure geometry checks...")

            # check the internal srs of the file
            _int_srs = check_internal_srs(
                data.get_srs(),
                path.name,
            )

            # check if file srs is the same as the model srs
            if not check_vs_srs(self.srs, data.get_srs()):
                logger.warning(
                    f"Spatial reference of '{path.name}' \
('{get_srs_repr(data.get_srs())}') does not match \
the model spatial reference ('{get_srs_repr(self.srs)}')"
                )
                logger.info(f"Reprojecting '{path.name}' to '{get_srs_repr(self.srs)}'")
                data = geom.reproject(data, self.srs.ExportToWkt())

            # check if it falls within the extent of the hazard map
            check_geom_extent(
                data.bounds,
                self.hazard_grid.bounds,
            )

            # Add to the dict
            _d[file.rsplit(".", 1)[1]] = data
        # When all is done, add it
        self.exposure_geoms = _d

    def resolve(
        self,
    ):
        """Create permanent output.

        This is done but reading, loading and sorting the temporary output within
        the `.tmp` folder within the output folder. \n

        - This method might become private.
        """
        # Setup the locks for the worker
        csv_lock = self._mp_manager.Lock()
        geom_lock = self._mp_manager.Lock()

        # Setting up the jobs for resolving
        jobs = generate_jobs(
            {
                "cfg": self.cfg,
                "exp_data": self.exposure_data,
                "exp_geom": self.exposure_geoms,
                "chunk": self.chunks,
                "csv_lock": csv_lock,
                "geom_lock": geom_lock,
            },
        )

        # Execute the jobs
        logger.info("Busy...")
        execute_pool(
            ctx=self._mp_ctx,
            func=worker_csv.worker_ead,
            jobs=jobs,
            threads=self.nthreads,
        )

    def run(
        self,
    ):
        """Run the geometry model with provided settings.

        Generates output in the specified `output.path` directory.
        """
        # Create the output files
        self._setup_output_files()

        # Get band names for logging
        _nms = self.cfg.get("hazard.band_names")

        # Setup the mp logger for missing stuff
        _receiver = setup_mp_log(
            self._queue, "missing", level=2, dst=self.cfg.get("output.path")
        )
        logger.info("Starting the calculations")

        # Start the receiver (which is in a seperate thread)
        _receiver.start()

        # Setup the jobs
        # First setup the locks
        locks = [self._mp_manager.Lock() for _ in range(self.hazard_grid.size)]
        jobs = generate_jobs(
            {
                "cfg": self.cfg,
                "queue": self._queue,
                "haz": self.hazard_grid,
                "idx": range(1, self.hazard_grid.size + 1),
                "vul": self.vulnerability_data,
                "exp_geom": self.exposure_geoms,
                "chunk": self.chunks,
                "lock": locks,
            },
            tied=["idx", "lock"],
        )

        logger.info(f"Using number of threads: {self.nthreads}")

        # Execute the jobs in a multiprocessing pool
        _s = time.time()
        logger.info("Busy...")
        execute_pool(
            ctx=self._mp_ctx,
            func=worker_csv.worker,
            jobs=jobs,
            threads=self.nthreads,
        )
        _e = time.time() - _s

        logger.info(f"Calculations time: {round(_e, 2)} seconds")
        # After the calculations are done, close the receiver
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

        logger.info("Producing model output from temporary files")
        # Patch output from the seperate processes back together
        self.resolve()
        logger.info(f"Output generated in: '{self.cfg.get('output.path')}'")

        if not self._keep_temp:
            logger.info("Deleting temporary files...")
            self._clean_up()

        logger.info("Geom calculation are done!")
