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
    check_hazard_subsets,
    check_internal_srs,
    check_vs_srs,
)
from fiat.fio import GridIO, open_csv, open_grid
from fiat.gis import grid
from fiat.log import spawn_logger
from fiat.struct import Table
from fiat.util import (
    HAZARD_FILE,
    NEED_IMPLEMENTED,
    VULNERABILITY_FILE,
    generic_path_check,
    get_srs_repr,
)

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
        self.hazard: GridIO | None = None
        self.vulnerability: Table | None = None

        # Type of calculations
        self.type = self.cfg.get("hazard.type", "flood")
        self.module = importlib.import_module(f"fiat.methods.{self.type}")
        # Risk or event based
        self.risk = self.cfg.get("model.risk", False)

        # Threading stuff
        self._mp_ctx = get_context("spawn")
        self._mp_manager = None
        self._queue = None
        self._threads = 1

        ## Call the necessary methods at init
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
        return self.cfg.get("hazard.type")

    @type.setter
    def type(self, value: str):
        """Set the hazard type."""
        self.cfg.set("hazard.type", value)
        self.module = importlib.import_module(f"fiat.methods.{value}")

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
        # Sort the pathing
        # Hierarchy: 1) signature, 2) configurations
        path = path or self.cfg.get(HAZARD_FILE)
        if path is None:
            return
        path = generic_path_check(path, root=self.cfg.path)
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

        if not self.cfg.get("model.srs.global", False):
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
            _resalg = self.cfg.get("hazard.resalg", 0)
            data = grid.reproject(
                data,
                dst_srs=self.srs.ExportToWkt(),
                resample=_resalg,
            )

        # Reset to ensure the entry is present
        self.cfg.set(HAZARD_FILE, path)
        # When all is done, add it
        self.hazard = data

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
            Path to the vulnerabulity data, by default None.
        **kwargs : dict, optional
            Keyword arguments for reading. These are passed into [open_csv]\
(/api/fio/open_csv.qmd) after which into [Table](/api/Table.qmd)/.
        """
        # Sort the pathing
        # Hierarchy: 1) signature, 2) configurations
        path = path or self.cfg.get(VULNERABILITY_FILE)
        if path is None:
            return
        path = generic_path_check(path, root=self.cfg.path)
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
        step_size = self.cfg.get("vulnerability.step_size", 0.01)
        self.cfg.set("vulnerability.step_size", step_size)
        logger.info(
            f"Upscaling vulnerability curves, \
using a step size of: {step_size}"
        )
        data.upscale(step_size, inplace=True)

        # Reset to ensure the entry is present
        self.cfg.set(VULNERABILITY_FILE, path)
        # When all is done, add it
        self.vulnerability = data

    ## Run
    @abstractmethod
    def run(
        self,
    ):
        """Run model."""
        raise NotImplementedError(NEED_IMPLEMENTED)
