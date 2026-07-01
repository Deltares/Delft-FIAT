"""Base model of FIAT."""

import importlib
from abc import ABCMeta, abstractmethod
from multiprocessing import get_context
from multiprocessing.queues import Queue
from os import cpu_count
from pathlib import Path

from pyproj.crs import CRS

from fiat.cfg import Configurations
from fiat.check import (
    check_duplicate_columns,
    check_internal_crs,
    check_vs_srs,
)
from fiat.fio import Dataset
from fiat.gis import grid
from fiat.log import spawn_logger
from fiat.open import open_csv, open_grid
from fiat.struct import Table
from fiat.typing import MethodType
from fiat.util import (
    DEPTH,
    FIAT_METHOD,
    FLOOD_DEPTH,
    HAZARD_FILE,
    HAZARD_RESALG,
    HAZARD_SETTINGS,
    INDEX,
    MODEL_CALC,
    MODEL_GRID_CHUNK,
    MODEL_RISK,
    MODEL_SRS_FORCE,
    MODEL_SRS_VALUE,
    MODEL_THREADS,
    NEED_IMPLEMENTED,
    VULNERABILITY_FILE,
    VULNERABILITY_SETTINGS,
    generic_path_check,
    get_crs_repr,
)

logger = spawn_logger(__name__)


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
        self._crs: CRS | None = None
        self.hazard: Dataset | None = None
        self.vulnerability: Table | None = None

        # Type of calculations
        self._type: str = self.cfg.get(MODEL_CALC, FLOOD_DEPTH)
        self.method: MethodType = importlib.import_module(f"{FIAT_METHOD}.{self.type}")
        # Risk or event based
        self._risk: bool = self.cfg.get(MODEL_RISK, False)

        # Threading stuff
        self.ctx = get_context("spawn")
        self.queue = Queue(maxsize=1000, ctx=self.ctx)
        self.shm = None
        self._threads: int = 1

        ## Call the necessary methods at init
        self._crs = self.cfg.get(MODEL_SRS_VALUE, "EPSG:4326")
        self.threads = self.cfg.get(MODEL_THREADS)
        self.read_hazard()
        self.read_vulnerability()

    @abstractmethod
    def __del__(self):
        self._srs = None

    def __repr__(self):
        return f"<{self.__class__.__name__} object at {id(self):#018x}>"

    ## Properties
    @property
    def crs(self) -> CRS:
        """Return the model srs."""
        return CRS.from_user_input(self._crs)

    @crs.setter
    def crs(self, value: str):
        """Set the model spatial reference system.

        Parameters
        ----------
        crs : str
            The spatial reference system described by a string (e.g. 'EPSG:4326'),
            by default None
        """
        # Infer the spatial reference system
        try:
            CRS.from_user_input(value)
            self._crs = value
        except BaseException as e:
            raise e

    @property
    def risk(self) -> bool:
        """Return the calculation modus."""
        return self._risk

    @risk.setter
    def risk(self, value: bool):
        """Set the calculation modus."""
        self._risk = value

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
        return self._type

    @type.setter
    def type(self, value: str):
        """Set the hazard type."""
        self._type = value
        self.method = importlib.import_module(f"{FIAT_METHOD}.{value}")

    ## Read data methods
    def read_hazard(
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
(/api/fio/open_grid.qmd) after which into [Dataset](/api/Dataset.qmd)/
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
            self.cfg.generate_kwargs(HAZARD_SETTINGS),
        )
        kw.update(
            self.cfg.generate_kwargs(MODEL_GRID_CHUNK),
        )
        kw.update(**kwargs)
        data = open_grid(path, **kw)
        ## checks
        logger.info("Executing hazard checks...")

        # check the internal srs of the file
        check_internal_crs(
            data.crs,
            path.name,
        )

        if not self.cfg.get(MODEL_SRS_FORCE, False):
            logger.warning("Setting the model srs from the hazard data.")
            self.crs = data.crs.to_wkt()

        # check if file srs is the same as the model srs
        if not check_vs_srs(self.crs, data.crs):
            logger.warning(
                f"Spatial reference of '{path.name}' \
('{get_crs_repr(data.crs)}') does not match the \
model spatial reference ('{get_crs_repr(self.crs)}')"
            )
            logger.info(f"Reprojecting '{path.name}' to '{get_crs_repr(self.crs)}'")
            _resalg = self.cfg.get(HAZARD_RESALG, "nearest")
            data = grid.reproject(
                data,
                dst_crs=self.crs.to_wkt(),
                method=_resalg,
            )

        # Reset to ensure the entry is present
        self.cfg.set(HAZARD_FILE, path)
        # When all is done, add it
        self.hazard = data

    def read_vulnerability(
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
        kw = {INDEX: DEPTH}
        kw.update(
            self.cfg.generate_kwargs(VULNERABILITY_SETTINGS),
        )
        kw.update(kwargs)  # Update with user defined method input
        data = open_csv(str(path), **kw)
        ## checks
        logger.info("Executing vulnerability checks...")

        # Column check
        check_duplicate_columns(data.duplicate_columns)

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
