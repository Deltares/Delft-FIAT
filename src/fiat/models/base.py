"""Base model of FIAT."""

import importlib
from abc import ABCMeta, abstractmethod
from multiprocessing import get_context
from os import cpu_count
from pathlib import Path

from osgeo import osr

from fiat.cfg import Configurations
from fiat.check import (
    check_duplicate_columns,
    check_hazard_band_names,
    check_hazard_rp,
    check_hazard_subsets,
    check_internal_srs,
    check_vs_srs,
)
from fiat.fio import GeomIO, GridIO, open_csv, open_grid
from fiat.fio.util import deter_band_names
from fiat.gis import grid
from fiat.log import spawn_logger
from fiat.models.util import check_file_for_read
from fiat.struct import Table, TableLazy
from fiat.util import NEED_IMPLEMENTED, deter_dec, get_srs_repr

logger = spawn_logger("fiat.model")


class BaseModel(metaclass=ABCMeta):
    """Base template for the model objects.

    Parameters
    ----------
    cfg : Configurations
        Configuration object, derived from dictionary.
    """

    def __init__(
        self,
        cfg: Configurations,
    ):
        self.cfg = cfg
        logger.info(f"Using settings from '{self.cfg.filepath}'")

        ## Declarations
        # Model data
        self._srs: osr.SpatialReference | None = None
        self.exposure_data: dict[int, TableLazy] | None = None
        self.exposure_geoms: dict[int, GeomIO] | None = None
        self.exposure_grid: GridIO | None = None
        self.hazard_grid: GridIO | None = None
        self.vulnerability_data: Table | None = None
        # Type of calculations
        type = self.cfg.get("model.type", "flood")
        self.module = importlib.import_module(f"fiat.methods.{type}")
        self.cfg.set("model.type", type)
        # Risk or event based
        risk = self.cfg.get("model.risk", False)
        self.cfg.set("model.risk", risk)
        # Vulnerability data
        self._vul_step_size = 0.01
        self._rounding = 2
        self.cfg.set("vulnerability.round", self._rounding)
        # Threading stuff
        self._mp_ctx = get_context("spawn")
        self._mp_manager = None
        self._queue = None
        self._threads = 1
        self.chunks = []

        # Call the necessary methods at init
        self.srs = self.cfg.get("model.srs.value", "EPSG:4326")
        self.threads = self.cfg.get("model.threads")
        self.read_hazard_grid()
        self.read_vulnerability_data()

    @abstractmethod
    def __del__(self):
        self._srs = None

    def __repr__(self):
        return f"<{self.__class__.__name__} object at {id(self):#018x}>"

    ## Properties
    @property
    def risk(self) -> bool:
        """Return the calculation modus."""
        return self.cfg.get("model.risk")

    @risk.setter
    def risk(self, value: bool):
        """Set the calculation modus."""
        self.cfg.set("model.risk", value)

    @property
    def srs(self) -> osr.SpatialReference:
        """Return the model srs."""
        return self._srs

    @srs.setter
    def srs(self, value: str):
        """Set the model spatial reference system.

        Parameters
        ----------
        srs : str
            The spatial reference system described by a string (e.g. 'EPSG:4326'),
            by default None
        """
        # Infer the spatial reference system
        self._srs = osr.SpatialReference()
        self._srs.SetFromUserInput(value)

        # Set crs for later use
        self.cfg.set("model.srs.value", get_srs_repr(self._srs))
        logger.info(f"Model srs set to: '{get_srs_repr(self._srs)}'")

    @property
    def threads(self) -> int:
        """Return the number of threads to be used."""
        return self._threads

    @threads.setter
    def threads(self, n: int | None):
        """Set the number of threads.

        Either through the config file, cli or directly.

        Parameters
        ----------
        n : int
            Number of threads.
        """
        max_threads = cpu_count()
        if n is not None:
            if n > max_threads:
                logger.warning(
                    f"Given number of threads ('{n}') \
exceeds machine thread count ('{max_threads}')"
                )
            self._threads = min(max_threads, n)

        logger.info(f"Using number of threads: {self._threads}")

    @property
    def type(self) -> str:
        """Return the hazard type."""
        return self.cfg.get("model.type")

    @type.setter
    def type(self, value: str):
        """Set the hazard type."""
        self.cfg.set("model.type", value)
        self.module = importlib.import_module(f"fiat.methods.{value}")

    ## Set(up) methods.
    @abstractmethod
    def _setup_output_files(
        self,
    ):
        """Set up output files."""
        raise NotImplementedError(NEED_IMPLEMENTED)

    ## Read data methods
    def read_hazard_grid(
        self,
        path: Path | str = None,
        **kwargs: dict,
    ) -> None:
        """Read the hazard data.

        If no path is provided the method tries to
        infer it from the model configurations.

        Parameters
        ----------
        path : Path | str, optional
            Path to the hazard gridded dataset, by default None
        kwargs : dict, optional
            Keyword arguments for reading. These are passed into [open_grid]\
(/api/fio/open_grid.qmd) after which into [GridIO](/api/GridIO.qmd)/
        """
        file_entry = "hazard.file"
        path = check_file_for_read(self.cfg, file_entry, path)
        if path is None:
            return
        logger.info(f"Reading hazard data ('{path.name}')")

        # Set the extra arguments from the settings file
        kw = {}
        kw.update(
            self.cfg.generate_kwargs("hazard.settings"),
        )
        kw.update(
            self.cfg.generate_kwargs("model.grid.chunk"),
        )
        kw.update(**kwargs)
        data = open_grid(path, **kw)
        ## checks
        logger.info("Executing hazard checks...")

        # check for subsets
        check_hazard_subsets(
            data.subdatasets,
            path,
        )

        # check the internal srs of the file
        check_internal_srs(
            data.srs,
            path.name,
        )

        if not self.cfg.get("model.srs.prefer_global", False):
            logger.warning("Setting the model srs from the hazard data.")
            self.srs = get_srs_repr(data.srs)

        # check if file srs is the same as the model srs
        if not check_vs_srs(self.srs, data.srs):
            logger.warning(
                f"Spatial reference of '{path.name}' \
('{get_srs_repr(data.srs)}') does not match the \
model spatial reference ('{get_srs_repr(self.srs)}')"
            )
            logger.info(f"Reprojecting '{path.name}' to '{get_srs_repr(self.srs)}'")
            _resalg = self.cfg.get("hazard.resampling_method", 0)
            data = grid.reproject(
                data,
                dst_srs=self.srs.ExportToWkt(),
                resample=_resalg,
            )

        # check risk return periods
        if self.risk:
            band_rps = [
                data[idx].get_metadata_item("return_period") for idx in range(data.size)
            ]
            rp = check_hazard_rp(
                band_rps,
                self.cfg.get("hazard.return_periods"),
                path,
            )
            self.cfg.set("hazard.return_periods", rp)

        # Information for output
        ns = check_hazard_band_names(
            deter_band_names(data),
            self.risk,
            self.cfg.get("hazard.return_periods"),
            data.size,
        )
        self.cfg.set("hazard.band_names", ns)

        # Reset to ensure the entry is present
        self.cfg.set(file_entry, path)
        # When all is done, add it
        self.hazard_grid = data

    def read_vulnerability_data(
        self,
        path: Path | str = None,
        **kwargs: dict,
    ):
        """Read the vulnerability data.

        If no path is provided the method tries to
        infer it from the model configurations.

        Parameters
        ----------
        path : Path | str, optional
            Path to the vulnerabulity data, by default None
        kwargs : dict, optional
            Keyword arguments for reading. These are passed into [open_csv]\
(/api/fio/open_csv.qmd) after which into [Table](/api/Table.qmd)/
        """
        file_entry = "vulnerability.file"
        path = check_file_for_read(self.cfg, file_entry, path)
        if path is None:
            return
        logger.info(f"Reading vulnerability curves ('{path.name}')")

        # Setting the keyword arguments from settings file
        kw = {"index": "water depth"}
        kw.update(
            self.cfg.generate_kwargs("vulnerability.settings"),
        )
        kw.update(kwargs)  # Update with user defined method input
        data = open_csv(str(path), **kw)
        ## checks
        logger.info("Executing vulnerability checks...")

        # Column check
        check_duplicate_columns(data.duplicate_columns)

        # upscale the data (can be done after the checks)
        if "vulnerability.step_size" in self.cfg:
            self._vul_step_size = self.cfg.get("vulnerability.step_size")
            self._rounding = deter_dec(self._vul_step_size)
            self.cfg.set("vulnerability.round", self._rounding)

        logger.info(
            f"Upscaling vulnerability curves, \
using a step size of: {self._vul_step_size}"
        )
        data.upscale(self._vul_step_size, inplace=True)

        # Reset to ensure the entry is present
        self.cfg.set(file_entry, path)
        # When all is done, add it
        self.vulnerability_data = data

    ## Run
    @abstractmethod
    def run(
        self,
    ):
        """Run model."""
        raise NotImplementedError(NEED_IMPLEMENTED)
