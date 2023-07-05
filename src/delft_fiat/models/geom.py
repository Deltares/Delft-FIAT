from delft_fiat.check import check_srs
from delft_fiat.gis import geom, overlay
from delft_fiat.gis.crs import get_srs_repr
from delft_fiat.io import (
    BufferTextHandler,
    GeomMemFileHandler,
    open_csv,
    open_exp,
    open_geom,
)
from delft_fiat.log import spawn_logger
from delft_fiat.models.base import BaseModel
from delft_fiat.models.calc import calc_risk
from delft_fiat.models.util import geom_worker
from delft_fiat.util import NEWLINE_CHAR

import os
import time
from concurrent.futures import ProcessPoolExecutor, wait, as_completed
from multiprocessing import Process
from pathlib import Path

logger = spawn_logger("fiat.model.geom")


class GeomModel(BaseModel):
    """GeomModel class."""

    _method = {
        "area": overlay.clip,
        "centroid": overlay.pin,
    }

    def __init__(
        self,
        cfg: "ConfigReader",
    ):
        """Initialize the GeomModel class.

        Parameters
        ----------
        cfg : ConfigReader
            _description_
        """

        # Initialize the base class
        super().__init__(cfg)

        # Read the hazard grid
        self._read_exposure_data()
        self._read_exposure_geoms()

    def __del__(self):
        """Destructor."""

        BaseModel.__del__(self)

    def _clean_up(self):
        """Clean up the temporary files."""

        _p = self._cfg.get("output.path.tmp")
        for _f in _p.glob("*"):
            os.unlink(_f)
        os.rmdir(_p)

    def _read_exposure_data(self):
        """Read the exposure data."""

        # Read the exposure data
        path = self._cfg.get("exposure.geom.csv")
        logger.info(f"Reading exposure data ('{path.name}')")
        data = open_exp(path, index="Object ID")

        ## TODO: Add validity checks here
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
        """Read the exposure geometries and store in the object as a dict."""

        # Initialize the dict
        _d = {}

        # List all the exposure geometrie files
        _found = [item for item in list(self._cfg) if "exposure.geom.file" in item]

        # Loop over the files
        for file in _found:
            # Read the file
            path = self._cfg.get(file)
            logger.info(
                f"Reading exposure geometry '{file.split('.')[-1]}' ('{path.name}')"
            )
            data = open_geom(str(path))

            # TODO: Add validity checks here
            logger.info("Executing exposure geometry checks...")

            # Check the spatial reference, reprojection if needed
            if not check_srs(self.srs, data.get_srs(), path.name):
                logger.warning(
                    f"Spatial reference of '{path.name}' ('{get_srs_repr(data.get_srs())}') \
does not match the model spatial reference ('{get_srs_repr(self.srs)}')"
                )
                logger.info(f"Reprojecting '{path.name}' to '{get_srs_repr(self.srs)}'")
                data = geom.reproject(data, self.srs.ExportToWkt())

            ## Add the data to the dict
            _d[file.rsplit(".", 1)[1]] = data

        ## When all is done, add the exposure data as a dictionary of ExposureTable objects
        self._exposure_geoms = _d

    def _patch_up(
        self,
    ):
        """Remove the temporary files and patch up the output files."""

        # Collect the required files
        _exp = self._exposure_data
        _gm = self._exposure_geoms
        _risk = self._cfg.get("hazard.risk")
        _rp_coef = self._cfg.get("hazard.rp_coefficients")
        _new_cols = self._cfg["output.new_columns"]
        _files = {}
        header = b""

        # Collect the output file names
        out_csv = "output.csv"
        if "output.csv.name" in self._cfg:
            out_csv = self._cfg["output.csv.name"]

        # Create the output file
        writer = BufferTextHandler(
            Path(self._cfg["output.path"], out_csv),
            buffer_size=100000,
        )
        header += ",".join(_exp.columns).encode() + b","
        header += ",".join(_new_cols).encode()
        header += NEWLINE_CHAR.encode()
        writer.write(header)

        # Collect the temporary files
        _paths = Path(self._cfg.get("output.path.tmp")).glob("*.dat")

        for p in _paths:
            _d = open_csv(p, index=_exp.meta["index_name"], large=True)
            _files[p.stem] = _d
            _d = None

        for key, gm in _gm.items():
            _add = key[-1]
            out_geom = f"spatial{_add}.gpkg"

            # Check if the output file name is defined in the config file
            if f"output.geom.name{_add}" in self._cfg:
                out_geom = self._cfg[f"output.geom.name{_add}"]

            # Create the output file
            geom_writer = GeomMemFileHandler(
                Path(self._cfg["output.path"], out_geom),
                self.srs,
                gm.layer.GetLayerDefn(),
            )

            geom_writer.create_fields(zip(_new_cols, ["float"] * len(_new_cols)))

            # Loop over the features and write the data to the output file
            for ft in gm:
                row = b""

                oid = ft.GetField(0)
                row += _exp[oid].strip()
                vals = []

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

            # Flush the geometry file
            geom_writer.dump2drive()
            geom_writer = None

        # Flush the output file
        writer.flush()
        writer = None

        # Clean up the opened temporary files
        for _d in _files.keys():
            _files[_d] = None
        _files = None

    def run(
        self,
    ):
        """Run the model."""

        _nms = self._cfg.get("hazard.band_names")
        logger.info("Starting the calculations")
        if self._hazard_grid.count > 1:
            # Check the available cores
            pcount = min(os.cpu_count(), self._hazard_grid.count)
            futures = []

            # Loop over the hazard grids. Initialize and run the workers
            with ProcessPoolExecutor(max_workers=pcount) as Pool:
                _s = time.time()
                for idx in range(self._hazard_grid.count):
                    logger.info(
                        f"Submitting a job for the calculations in regards to band: '{_nms[idx]}'"
                    )
                    fs = Pool.submit(
                        geom_worker,
                        self._cfg,
                        self._hazard_grid,
                        idx + 1,
                        self._vulnerability_data,
                        self._exposure_data,
                        self._exposure_geoms,
                    )
                    futures.append(fs)
            logger.info("Busy...")
            wait(futures)

        else:
            logger.info(f"Submitting a job for the calculations in a seperate process")
            _s = time.time()
            p = Process(
                target=geom_worker,
                args=(
                    self._cfg,
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

        logger.info("Producing model output from temporary files")
        self._patch_up()
        logger.info(f"Output generated in: '{self._cfg['output.path']}'")

        # Clean up the temporary files
        if not self._keep_temp:
            logger.info("Deleting temporary files...")
            self._clean_up()

        logger.info("All done!")
