"""Geom model of FIAT."""

import copy
import os
import re
import time
from multiprocessing import Manager
from pathlib import Path
from typing import List

from osgeo import ogr

from fiat.cfg import Configurations
from fiat.check import (
    check_duplicate_columns,
    check_exp_columns,
    check_exp_derived_types,
    check_exp_index_col,
    check_geom_extent,
    check_internal_srs,
    check_vs_srs,
)
from fiat.fio import (
    open_csv,
    open_geom,
)
from fiat.gis import geom
from fiat.log import setup_mp_log, spawn_logger
from fiat.models import worker_geom
from fiat.models.base import BaseModel
from fiat.models.util import (
    EXPOSURE_FIELDS,
    GEOM_DEFAULT_CHUNK,
    check_file_for_read,
    csv_def_file,
    execute_pool,
    generate_jobs,
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
    - exposure.csv.file
    - exposure.geom.file1
    - output.geom.file1

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
        self.exposure_types = self.cfg.get("exposure.types", ["damage"])

        # Setup the geometry model
        self.read_exposure()

    def __del__(self):
        BaseModel.__del__(self)

    def _discover_exposure_meta(
        self,
        columns: dict,
        meta: dict,
        index: int,
        index_col: str,
    ):
        """Simple method for sorting out the exposure meta."""  # noqa: D401
        # check if set from the csv file
        if -1 not in meta:
            meta[index] = {}
            # Check the exposure column headers
            check_exp_columns(
                index_col,
                columns=list(columns.keys()),
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
        """Set the chunking size."""
        # Determine maximum geometry dataset size
        max_geom_size = max(
            [item.size for item in self.exposure_geoms.values()],
        )
        # Set the 1D chunks
        self.chunks = create_1d_chunk(
            max_geom_size,
            self.threads,
        )
        # Set the write size chunking
        chunk_int = self.cfg.get("global.geom.chunk", GEOM_DEFAULT_CHUNK)
        self.cfg.set("global.geom.chunk", chunk_int)

    def _setup_output_files(self):
        """Set up the output files.

        These are the filled by running the model.
        """
        # Setup the geometry output files
        for key, gm in self.exposure_geoms.items():
            # Define outgoing dataset
            out_geom = self.cfg.get(f"output.geom.name{key}", f"spatial{key}.gpkg")
            self.cfg.set(f"output.geom.name{key}", out_geom)
            # Get the new fields per geometry file
            new_fields = tuple(self.cfg.get("_exposure_meta")[key]["new_fields"])
            # Open and write a layer with the necessary fields
            with open_geom(
                Path(self.cfg.get("output.path"), out_geom), mode="w", overwrite=True
            ) as _w:
                _w.create_layer(self.srs, gm.geom_type)
                _w.create_fields(dict(zip(gm.fields, gm.dtypes)))
                _w.create_fields(dict(zip(new_fields, [ogr.OFTReal] * len(new_fields))))
            _w = None

            # Check whether to do the same for the csv
            out_csv = self.cfg.get(f"output.csv.name{key}")
            if out_csv is not None:
                columns = ("object_id",) + new_fields
                if self.exposure_data is not None:
                    columns = self.exposure_data.columns + tuple(
                        self.cfg.get("_exposure_meta")[-1]["new_fields"]
                    )

                # Create an empty csv file for the separate thread to till
                csv_def_file(
                    Path(self.cfg.get("output.path"), out_csv),
                    columns,
                )

    def get_exposure_meta(self):
        """Get the exposure meta regarding the data itself (fields etc.)."""
        # Get the relevant column headers
        meta = {}
        if self.exposure_data is not None:
            self._discover_exposure_meta(
                self.exposure_data._columns,
                meta,
                -1,
                self.cfg.get("exposure.csv.settings.index"),
            )
        for key, gm in self.exposure_geoms.items():
            columns = gm._columns
            self._discover_exposure_meta(
                columns,
                meta,
                key,
                self.cfg.get("exposure.geom.settings.index"),
            )
        self.cfg.set("_exposure_meta", meta)

    def read_exposure(self):
        """Read all the exposure files."""
        self.read_exposure_geoms()
        self.read_exposure_data()

    def read_exposure_data(
        self,
        path: Path | str = None,
        **kwargs: dict,
    ):
        """Read the exposure data file (csv).

        If no path is provided the method tries to
        infer it from the model configurations.

        Parameters
        ----------
        path : Path | str, optional
            Path to the exposure data, by default None
        kwargs : dict, optional
            Keyword arguments for reading. These are passed into [open_csv]\
(/api/fio/open_csv.qmd) after which into [TableLazy](/api/TableLazy.qmd)/
        """
        file_entry = "exposure.csv.file"
        path = check_file_for_read(self.cfg, file_entry, path)
        if path is None:
            return
        logger.info(f"Reading exposure data ('{path.name}')")

        # Setting the keyword arguments from settings file
        kw = {"index": "object_id"}
        kw.update(
            self.cfg.generate_kwargs("exposure.csv.settings"),
        )
        kw.update(kwargs)
        self.cfg.set("exposure.csv.settings.index", kw["index"])
        data = open_csv(path, lazy=True, **kw)
        ##checks
        logger.info("Executing exposure data checks...")

        # Check for duplicate columns
        check_duplicate_columns(data.meta["dup_cols"])

        # Reset to ensure the entry is present
        self.cfg.set(file_entry, path)
        ## When all is done, add it
        self.exposure_data = data

    def read_exposure_geoms(
        self,
        paths: List[Path] = None,
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
(/api/fio/open_geom.qmd) after which into [GeomSource](/api/GeomSource.qmd)/
        """
        # Discover the files
        _d = {}

        if paths is None:
            # TODO find maybe a better solution of defining this in the settings file
            files = [item for item in list(self.cfg) if "exposure.geom.file" in item]
            files = [item for item in files if re.match(r"^(.*)file(\d+)", item)]
            paths = [self.cfg.get(item) for item in files]
        else:
            files = [f"exposure.geom.file{idx+1}" for idx in range(len(paths))]

        # First check for the index_col
        index_col = self.cfg.get("exposure.geom.settings.index", "object_id")
        self.cfg.set("exposure.geom.settings.index", index_col)

        kw = {}
        kw.update(
            {"srs": self.cfg.get("exposure.geom.settings.srs")},
        )
        kw.update(kwargs)

        # For all that is found, try to read the data
        for file, path in zip(files, paths):
            suffix = int(re.findall(r"\d+", file.rsplit(".", 1)[1])[0])
            logger.info(
                f"Reading exposure geometry '{file.split('.')[-1]}' ('{path.name}')"
            )
            data = open_geom(path.as_posix(), **kw)
            ## checks
            logger.info("Executing exposure geometry checks...")

            # check for the index column
            check_exp_index_col(data, index_col=index_col)

            # check the internal srs of the file
            check_internal_srs(
                data.srs,
                path.name,
            )

            # check if file srs is the same as the model srs
            if not check_vs_srs(self.srs, data.srs):
                logger.warning(
                    f"Spatial reference of '{path.name}' \
('{get_srs_repr(data.srs)}') does not match \
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
            # And reset the entry
            self.cfg.set(f"exposure.geom.file{suffix}", path)
        # When all is done, add it
        self.exposure_geoms = _d

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

        # Exposure fields get function
        field_func = EXPOSURE_FIELDS[self.exposure_data is None]

        # Setup the jobs
        # First setup the locks
        lock1, lock2 = (None, None)
        if self.threads != 1:
            lock1, lock2 = [self._mp_manager.Lock()] * 2
        jobs = generate_jobs(
            {
                "cfg": self.cfg,
                "queue": self._queue,
                "haz": self.hazard_grid,
                "vul": self.vulnerability_data,
                "exp_func": field_func,
                "exp_data": self.exposure_data,
                "exp_geom": self.exposure_geoms,
                "chunk": self.chunks,
                "lock1": lock1,
                "lock2": lock2,
            },
            # tied=["idx", "lock"],
        )

        # Execute the jobs in a multiprocessing pool
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

        # Shutdown the manager
        self._mp_manager.shutdown()
