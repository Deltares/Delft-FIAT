"""Geom model of FIAT."""

import os
import sys
import time
from multiprocessing import Manager
from pathlib import Path

from osgeo import ogr

from fiat.cfg import Configurations
from fiat.check import (
    check_exp_columns,
    check_exp_derived_types,
    check_exp_index_col,
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
from fiat.models import worker_geom
from fiat.models.base import BaseModel
from fiat.models.util import (
    GEOM_DEFAULT_CHUNK,
    check_file_for_read,
)
from fiat.util import (
    create_1d_chunk,
    discover_exp_columns,
    generate_output_columns,
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
        self.exposure_types: list[str] = self.cfg.get("exposure.types", ["damage"])

        # Setup the geometry model
        self.read_exposure()

    def __del__(self):
        BaseModel.__del__(self)

    ## Set(up) methods
    def _discover_exposure_meta(
        self,
        columns: dict,
        meta: dict,
        index: int,
        index_col: str,
    ):
        """Simple method for sorting out the exposure meta."""  # noqa: D401
        meta[index] = {}
        # Check the exposure column headers
        check_exp_columns(
            list(columns.keys()),
            index_col=index_col,
            mandatory_columns=getattr(self.module, "MANDATORY_COLUMNS"),
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
        if self.risk:
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

        # Set the indices for the outgoing columns
        idxs = list(range(len(columns), len(columns) + len(new_fields)))
        meta[index].update({"idxs": idxs})

    def _set_chunking(self):
        """Set the chunking size."""
        # Determine maximum geometry dataset size
        max_geom_size = max(
            [item.layer.size for item in self.exposure_geoms.values()],
        )
        # Set the 1D chunks
        self.chunks = create_1d_chunk(
            max_geom_size,
            self.threads,
        )
        # Set the write size chunking
        chunk_int = self.cfg.get("model.geom.chunk", GEOM_DEFAULT_CHUNK)
        self.cfg.set("model.geom.chunk", chunk_int)

    def _setup_output_files(self):
        """Set up the output files.

        These are the filled by running the model.
        """
        # Setup the geometry output files
        for key, gm in self.exposure_geoms.items():
            # Define outgoing dataset
            out_geom = self.cfg.get(
                f"output.geom.name{key}",
                f"spatial{key}{gm.path.suffix}",
            )
            self.cfg.set(f"output.geom.name{key}", out_geom)
            # Get the new fields per geometry file
            new_fields = tuple(self.cfg.get("_exposure_meta")[key]["new_fields"])
            # Open and write a layer with the necessary fields
            with open_geom(
                Path(self.cfg.get("output.path"), out_geom), mode="w", overwrite=True
            ) as _w:
                _w.create_layer(self.srs, gm.layer.geom_type)
                _w.layer.create_fields(dict(zip(gm.layer.fields, gm.layer.dtypes)))
                _w.layer.create_fields(
                    dict(zip(new_fields, [ogr.OFTReal] * len(new_fields)))
                )
            _w = None

    def get_exposure_meta(self):
        """Get the exposure meta regarding the data itself (fields etc.)."""
        # Get the relevant column headers
        meta = {}
        for key, item in self.exposure_geoms.items():
            self._discover_exposure_meta(
                item.layer._columns,
                meta=meta,
                index=key,
                index_col=self.cfg.get("exposure.geom.settings.index"),
            )
        self.cfg.set("_exposure_meta", meta)

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
        paths : List[Path], optional
            A list of paths to the vector files.
        kwargs : dict, optional
            Keyword arguments for reading. These are passed into [open_geom]\
(/api/fio/open_geom.qmd) after which into [GeomIO](/api/GeomIO.qmd)/
        """
        # First check for the index_col
        index_col = self.cfg.get("exposure.geom.settings.index", "object_id")
        self.cfg.set("exposure.geom.settings.index", index_col)

        kw = {}
        kw.update(
            {"srs": self.cfg.get("exposure.geom.settings.srs")},
        )
        kw.update(kwargs)

        # For all that is found, try to read the data
        path = check_file_for_read(
            self.cfg,
            entry="file",
            path=path,
        )
        logger.info(f"Reading exposure geometry ('{path.name}')")
        data = open_geom(path.as_posix(), **kw)
        ## checks
        logger.info("Executing exposure geometry checks...")

        # check for the index column
        check_exp_index_col(data.layer.columns, index_col=index_col, path=data.path)

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
            self.hazard_grid.bounds,
        )

        # Add to the dict
        # _d.append(data)
        # And reset the entry
        # self.cfg.set(file, path)

        # When all is done, add it
        # self.exposure_geoms = _d
        # self.exposure_data = {idx: None for idx in self.exposure_geoms}

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

        # Set the chunking
        self._set_chunking()

        # Create the output directory and files
        self.get_exposure_meta()
        self.cfg.setup_output_dir()
        self._setup_output_files()

        # Setup the mp logger for missing stuff
        _receiver = setup_mp_log(
            self._queue, "missing", level=2, dst=self.cfg.get("output.path")
        )
        logger.info("Starting the calculations")

        # Start the receiver (which is in a seperate thread)
        _receiver.start()

        # Setup the jobs
        # First setup the locks
        lock = None
        if self.threads != 1:
            lock = self._mp_manager.Lock()
        jobs = generate_jobs(
            {
                "cfg": self.cfg,
                "risk": self.risk,
                "haz": self.hazard_grid,
                "vul": self.vulnerability_data,
                "exp_data": self.exposure_geoms,
                "chunk": self.chunks,
                "queue": self._queue,
                "lock": lock,
            },
            # tied=["exp_data", "exp_geom", "idx"],
        )

        # Execute the jobs in a multiprocessing pool
        # Wrap to prevent weird error propagation with the pipes
        try:
            _s = time.time()
            logger.info("Busy...")
            execute_pool(
                ctx=self._mp_ctx,
                func=worker_geom.worker,
                jobs=jobs,
                threads=self.threads,
            )
            _e = time.time() - _s

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
