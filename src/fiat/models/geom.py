from delft_fiat.check import (
    check_geom_extent,
    check_internal_srs,
    check_vs_srs,
)
from delft_fiat.gis import geom, overlay
from delft_fiat.gis.crs import get_srs_repr
from delft_fiat.io import (
    BufferTextHandler,
    GeomMemFileHandler,
    open_csv,
    open_exp,
    open_geom,
)
from delft_fiat.log import Receiver, spawn_logger, setup_mp_log
from delft_fiat.models.base import BaseModel
from delft_fiat.models.calc import calc_risk
from delft_fiat.models.util import geom_worker
from delft_fiat.util import NEWLINE_CHAR

import os
import time
from concurrent.futures import ProcessPoolExecutor, wait, as_completed
from multiprocessing import Process, get_context
from multiprocessing.queues import Queue, SimpleQueue
from pathlib import Path

logger = spawn_logger("fiat.model.geom")


class GeomModel(BaseModel):
    _method = {
        "area": overlay.clip,
        "centroid": overlay.pin,
    }

    def __init__(
        self,
        cfg: "ConfigReader",
    ):
        """_summary_"""

        super().__init__(cfg)

        self._read_exposure_data()
        self._read_exposure_geoms()
        self._queue = self._mp_manager.Queue(maxsize=10000)

    def __del__(self):
        BaseModel.__del__(self)

    def _clean_up(self):
        """_summary_"""

        _p = self._cfg.get("output.path.tmp")
        for _f in _p.glob("*"):
            os.unlink(_f)
        os.rmdir(_p)

    def _read_exposure_data(self):
        """_summary_"""

        path = self._cfg.get("exposure.geom.csv")
        logger.info(f"Reading exposure data ('{path.name}')")
        data = open_exp(path, index="Object ID")
        ##checks
        logger.info("Executing exposure data checks...")

        ## Information for output
        _ex = None
        if self._cfg["hazard.risk"]:
            _ex = ["Risk (EAD)"]
        cols = data.create_all_columns(
            self._cfg.get("hazard.band_names"),
            _ex,
        )
        self._cfg["output.new_columns"] = cols

        ## When all is done, add it
        self._exposure_data = data

    def _read_exposure_geoms(self):
        """_summary_"""

        _d = {}
        _found = [item for item in list(self._cfg) if "exposure.geom.file" in item]
        for file in _found:
            path = self._cfg.get(file)
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
                    f"Spatial reference of '{path.name}' ('{get_srs_repr(data.get_srs())}') \
does not match the model spatial reference ('{get_srs_repr(self.srs)}')"
                )
                logger.info(f"Reprojecting '{path.name}' to '{get_srs_repr(self.srs)}'")
                data = geom.reproject(data, self.srs.ExportToWkt())

            # check if it falls within the extent of the hazard map
            check_geom_extent(
                data.bounds,
                self._hazard_grid.bounds,
            )

            # Add to the dict
            _d[file.rsplit(".", 1)[1]] = data
        # When all is done, add it
        self._exposure_geoms = _d

    def resolve(
        self,
    ):
        """_summary_"""

        # Setup some local referenced datasets and metadata
        _exp = self._exposure_data
        _gm = self._exposure_geoms
        _risk = self._cfg.get("hazard.risk")
        _rp_coef = self._cfg.get("hazard.rp_coefficients")
        # Reverse the _rp_coef to let them coincide with the acquired
        # values from the temporary files
        if _rp_coef:
            _rp_coef.reverse()
        _new_cols = self._cfg["output.new_columns"]
        _files = {}

        # Define the outgoing file
        out_csv = "output.csv"
        if "output.csv.name" in self._cfg:
            out_csv = self._cfg["output.csv.name"]

        # Setup the write and write the header of the file
        writer = BufferTextHandler(
            Path(self._cfg["output.path"], out_csv),
            buffer_size=100000,
        )
        header = b""
        header += ",".join(_exp.columns).encode() + b","
        header += ",".join(_new_cols).encode()
        header += NEWLINE_CHAR.encode()
        writer.write(header)

        # Get all the temporary data paths
        _paths = Path(self._cfg.get("output.path.tmp")).glob("*.dat")

        # Open the temporary files lazy
        for p in _paths:
            _d = open_csv(p, index=_exp.meta["index_name"], large=True)
            _files[p.stem] = _d
            _d = None

        # Loop over all the geometry source files
        for key, gm in _gm.items():
            _add = key[-1]

            # Define outgoing dataset
            out_geom = f"spatial{_add}.gpkg"
            if f"output.geom.name{_add}" in self._cfg:
                out_geom = self._cfg[f"output.geom.name{_add}"]

            # Setup the geometry writer
            geom_writer = GeomMemFileHandler(
                Path(self._cfg["output.path"], out_geom),
                self.srs,
                gm.layer.GetLayerDefn(),
            )
            geom_writer.create_fields(zip(_new_cols, ["float"] * len(_new_cols)))

            # Loop again over all the geometries
            for ft in gm:
                row = b""

                oid = ft.GetField(0)
                ft_info = _exp[oid]

                # If no data is found in the temporary files, write None values
                if ft_info is None:
                    geom_writer.add_feature(
                        ft,
                        dict(zip(_new_cols, [None] * len(_new_cols))),
                    )
                    row += f"{oid}".encode()
                    row += b"," * (len(_exp.columns) - 1)
                    row += NEWLINE_CHAR.encode()
                    writer.write(row)
                    continue

                row += ft_info.strip()
                vals = []

                # Loop over all the temporary files (loaded) to get the damage per object
                for item in _files.values():
                    row += b","
                    _data = item[oid].strip().split(b",", 1)[1]
                    row += _data
                    _val = [float(num.decode()) for num in _data.split(b",")]
                    vals += _val

                if _risk:
                    ead = round(
                        calc_risk(_rp_coef, vals[-1 :: -_exp._dat_len]),
                        self._rounding,
                    )
                    row += f",{ead}".encode()
                    vals.append(ead)
                row += NEWLINE_CHAR.encode()
                writer.write(row)
                geom_writer.add_feature(
                    ft,
                    dict(zip(_new_cols, vals)),
                )

            geom_writer.dump2drive()
            geom_writer = None

        writer.flush()
        writer = None

        # Clean up the opened temporary files
        for _d in _files.keys():
            _files[_d] = None
        _files = None

    def run(
        self,
    ):
        """_summary_"""

        # Get band names for logging
        _nms = self._cfg.get("hazard.band_names")

        # Setup the mp logger for missing stuff
        _receiver = setup_mp_log(
            self._queue, "missing", log_level=2, dst=self._cfg.get("output.path")
        )

        logger.info("Starting the calculations")

        # Start the receiver (which is in a seperate thread)
        _receiver.start()

        # If there are more than a hazard band in the dataset
        # Use a pool to execute the calculations
        if self._hazard_grid.count > 1:
            pcount = min(self.max_threads, self._hazard_grid.count)
            futures = []
            with ProcessPoolExecutor(max_workers=pcount) as Pool:
                _s = time.time()
                for idx in range(self._hazard_grid.count):
                    logger.info(
                        f"Submitting a job for the calculations in regards to band: '{_nms[idx]}'"
                    )
                    fs = Pool.submit(
                        geom_worker,
                        self._cfg,
                        self._queue,
                        self._hazard_grid,
                        idx + 1,
                        self._vulnerability_data,
                        self._exposure_data,
                        self._exposure_geoms,
                    )
                    futures.append(fs)
            logger.info("Busy...")
            # Wait for the children to finish their calculations
            wait(futures)
            # for p in p_s:
            #     p.join()

        # If there is only one hazard band present, call Process directly
        # No need for the extra overhead the Pool provides
        else:
            logger.info(f"Submitting a job for the calculations in a seperate process")
            _s = time.time()
            p = Process(
                target=geom_worker,
                args=(
                    self._cfg,
                    self._queue,
                    self._hazard_grid,
                    1,
                    self._vulnerability_data,
                    self._exposure_data,
                    self._exposure_geoms,
                ),
            )
            p.start()
            logger.info("Busy...")
            p.join()
        _e = time.time() - _s

        logger.info(f"Calculations time: {round(_e, 2)} seconds")
        # After the calculations are done, close the receiver
        _receiver.close()
        _receiver.close_handlers()
        if _receiver.count > 0:
            logger.warning(
                f"Some objects had missing data. For more info: 'missing.log' in '{self._cfg.get('output.path')}'"
            )
        else:
            os.unlink(
                Path(self._cfg.get("output.path"), "missing.log"),
            )

        logger.info("Producing model output from temporary files")
        # Patch output from the seperate processes back together
        self.resolve()
        logger.info(f"Output generated in: '{self._cfg['output.path']}'")

        if not self._keep_temp:
            logger.info("Deleting temporary files...")
            self._clean_up()

        logger.info("All done!")
