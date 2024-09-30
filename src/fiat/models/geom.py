"""Geom model of FIAT."""

import copy
import os
import re
import time
from pathlib import Path

from osgeo import ogr

from fiat.cfg import ConfigReader
from fiat.check import (
    check_duplicate_columns,
    check_exp_columns,
    check_exp_derived_types,
    check_geom_extent,
    check_internal_srs,
    check_vs_srs,
)
from fiat.gis import geom, overlay
from fiat.gis.crs import get_srs_repr
from fiat.io import (
    open_csv,
    open_geom,
)
from fiat.log import setup_mp_log, spawn_logger
from fiat.models import worker_geom
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

        # Set/ declare some variables
        self.exposure_types = self.cfg.get("exposure.types", ["damage"])

        # Setup the geometry model
        self.read_exposure()
        self.get_exposure_meta()
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

    def _discover_exposure_meta(
        self,
        columns: dict,
        meta: dict,
        index: int,
    ):
        """Simple method for sorting out the exposure meta."""  # noqa: D401
        # check if set from the csv file
        if -1 not in meta:
            meta[index] = {}
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
            meta[index].update({"types": types})

            ## Information for output
            extra = []
            if self.cfg.get("hazard.risk"):
                extra = ["ead"]
            new_fields, len1, total_idx = generate_output_columns(
                getattr(self.module, "NEW_COLUMNS"),
                types,
                extra=extra,
                suffix=self.cfg.get("hazard.band_names"),
            )
            meta[index].update(
                {
                    "new_fields": new_fields,
                    "slen": len1,
                    "total_idx": total_idx,
                }
            )
        else:
            meta[index] = copy.deepcopy(meta[-1])
            new_fields = meta[index]["new_fields"]

        # Set the indices for the outgoing columns
        idxs = list(range(len(columns), len(columns) + len(new_fields)))
        meta[index].update({"idxs": idxs})

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
            self.nchunk,
        )

    def _setup_output_files(self):
        """_summary_."""
        # Do the same for the geometry files
        for key, gm in self.exposure_geoms.items():
            # Define outgoing dataset
            out_geom = f"spatial{key}.fgb"
            if f"output.geom.name{key}" in self.cfg:
                out_geom = self.cfg.get(f"output.geom.name{key}")
            self.cfg.set(f"output.geom.name{key}", out_geom)
            # Open and write a layer with the necessary fields
            with open_geom(
                Path(self.cfg.get("output.path"), out_geom), mode="w", overwrite=True
            ) as _w:
                _w.create_layer(self.srs, gm.geom_type)
                _w.create_fields(dict(zip(gm.fields, gm.dtypes)))
                new = self.cfg.get("_exposure_meta")[key]["new_fields"]
                _w.create_fields(dict(zip(new, [ogr.OFTReal] * len(new))))
            _w = None

    def get_exposure_meta(self):
        """_summary_."""
        # Get the relevant column headers
        meta = {}
        if self.exposure_data is not None:
            self._discover_exposure_meta(
                self.exposure_data._columns,
                meta,
                -1,
            )
        for key, gm in self.exposure_geoms.items():
            columns = gm._columns
            self._discover_exposure_meta(columns, meta, key)
        self.cfg.set("_exposure_meta", meta)

    def read_exposure(self):
        """_summary_."""
        self.read_exposure_geoms()
        csv = self.cfg.get("exposure.csv.file")
        if csv is not None:
            self.read_exposure_data()

    def read_exposure_data(self):
        """_summary_."""
        path = self.cfg.get("exposure.csv.file")
        logger.info(f"Reading exposure data ('{path.name}')")

        # Setting the keyword arguments from settings file
        kw = {"index": "object_id"}
        kw.update(
            self.cfg.generate_kwargs("exposure.csv.settings"),
        )
        data = open_csv(path, large=True, **kw)
        ##checks
        logger.info("Executing exposure data checks...")

        # Check for duplicate columns
        check_duplicate_columns(data.meta["dup_cols"])

        ## When all is done, add it
        self.exposure_data = data

    def read_exposure_geoms(self):
        """_summary_."""
        # Discover the files
        _d = {}
        _found = [item for item in list(self.cfg) if "exposure.geom.file" in item]
        _found = [item for item in _found if re.match(r"^(.*)file(\d+)", item)]

        # For all that is found, try to read the data
        for file in _found:
            path = self.cfg.get(file)
            suffix = int(re.findall(r"\d+", file.rsplit(".", 1)[1])[0])
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
            _d[suffix] = data
        # When all is done, add it
        self.exposure_geoms = _d

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
        lock = self._mp_manager.Lock()
        jobs = generate_jobs(
            {
                "cfg": self.cfg,
                "queue": self._queue,
                "haz": self.hazard_grid,
                "vul": self.vulnerability_data,
                "exp_geom": self.exposure_geoms,
                "chunk": self.chunks,
                "lock": lock,
            },
            # tied=["idx", "lock"],
        )

        logger.info(f"Using number of threads: {self.nthreads}")

        # Execute the jobs in a multiprocessing pool
        _s = time.time()
        logger.info("Busy...")
        execute_pool(
            ctx=self._mp_ctx,
            func=worker_geom.worker,
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

        logger.info(f"Output generated in: '{self.cfg.get('output.path')}'")
        logger.info("Geom calculation are done!")
