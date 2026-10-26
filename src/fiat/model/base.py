"""Base model of FIAT."""

import importlib
import tomllib
from abc import ABCMeta, abstractmethod
from multiprocessing import get_context
from multiprocessing.queues import Queue
from pathlib import Path

from pyproj.crs import CRS

from fiat.check import (
    check_duplicate_columns,
    check_internal_crs,
    check_vs_crs,
)
from fiat.driver import NetcdfReader, Table
from fiat.gis import grid
from fiat.log import spawn_logger
from fiat.open import open_csv, open_grid
from fiat.settings import GeomSettings, GridSettings
from fiat.typing import MethodType
from fiat.util import (
    FIAT_METHOD,
    generic_directory_check,
    get_crs_repr,
)

logger = spawn_logger(__name__)


class BaseModel(metaclass=ABCMeta):
    """Base template for the model objects.

    Parameters
    ----------
    settings : GeomSettings | GridSettings
        Validated settings.
    """

    def __init__(
        self,
        settings: GeomSettings | GridSettings,
    ):
        self.settings = settings

        ## Declarations
        # Model data
        self._hazard: NetcdfReader | None = None
        self._vulnerability: Table | None = None

        # Type of calculations
        self._method: MethodType = importlib.import_module(
            f"{FIAT_METHOD}.{self.settings.method}",
        )

        # Threading stuff
        self.ctx = get_context("spawn")
        self.queue = Queue(maxsize=1000, ctx=self.ctx)

        ## Call the necessary methods at init
        logger.info(f"Using number of threads: {self.settings.threads}")
        self._read_vulnerability()
        self._read_hazard()

    def __repr__(self):
        return f"<{self.__class__.__name__} object at {id(self):#018x}>"

    ## Properties
    @property
    def crs(self) -> CRS:
        """Return the model crs."""
        return CRS.from_user_input(self.settings.projection.crs)

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
            self.settings.update(projection={"crs": value})
        except BaseException as e:
            raise e

    @property
    def hazard(self) -> NetcdfReader | None:
        """Return the hazard data."""
        return self._hazard

    @property
    def method(self) -> MethodType:
        """Return the current method module."""
        return self._method

    @property
    def risk(self) -> bool:
        """Return the calculation modus."""
        return self.settings.risk

    @risk.setter
    def risk(self, value: bool):
        """Set the calculation modus."""
        self.settings.update(risk=value)

    @property
    def threads(self) -> int:
        """Return the number of threads to be used."""
        return self.settings.threads

    @threads.setter
    def threads(self, n: int):
        """Set the number of threads.

        Either through the config file, cli or directly.

        Parameters
        ----------
        n : int
            Number of threads.
        """
        self.settings.update(threads=n)
        logger.info(f"Using number of threads: {self.settings.threads}")

    @property
    def type(self) -> str:
        """Return the hazard type."""
        return self.settings.type

    @property
    def vulnerability(self) -> Table | None:
        """Return the vulnerability data."""
        return self._vulnerability

    ## Class methods
    @classmethod
    def from_file(cls, file: Path | str):
        """Initialize the model from a settings file."""
        obj = cls()

        # Set the settings
        with open(file, "rb") as reader:
            settings = tomllib.load(reader)
            obj.settings.model_validate(settings)

        return obj

    ## Read data methods
    def _read_hazard(self) -> None:
        """Read the hazard data."""
        file = self.settings.hazard.file
        # Move on with distilling the read kwargs
        logger.info(f"Reading hazard data ('{file.name}')")

        # Get the kwargs from the model settings
        kwargs = self.settings.hazard.settings.model_dump(exclude_none=True)
        # Read the data
        data = open_grid(file, **kwargs)

        # checks
        logger.info("Executing hazard checks...")

        # check the internal crs of the file
        check_internal_crs(
            data.profile.crs,
            file.name,
        )

        if not self.settings.projection.force:
            logger.warning("Setting the model crs from the hazard data.")
            self.crs = data.profile.crs.to_wkt()

        # check if file crs is the same as the model crs
        if not check_vs_crs(self.crs, data.profile.crs):
            logger.warning(
                f"Spatial reference of '{file.name}' \
('{get_crs_repr(data.profile.crs)}') does not match the \
model spatial reference ('{get_crs_repr(self.crs)}')"
            )
            logger.info(f"Reprojecting '{file.name}' to '{get_crs_repr(self.crs)}'")
            _resalg = self.settings.hazard.resalg
            data = grid.reproject(
                data,
                dst_crs=self.crs.to_wkt(),
                method=_resalg,
            )

        # When all is done, add it
        self._hazard = data

    def _read_vulnerability(self):
        """Read the vulnerability data."""
        # Get the file path
        file = self.settings.vulnerability.file
        logger.info(f"Reading vulnerability curves ('{file.name}')")

        # Get the kwargs from the model settings
        kwargs = self.settings.vulnerability.settings.model_dump(exclude_none=True)
        # Read the data
        data = open_csv(file, **kwargs)

        ## checks
        logger.info("Executing vulnerability checks...")

        # Column check
        check_duplicate_columns(data.duplicate_columns)

        # When all is done, add it
        self._vulnerability = data

    ## Run
    @abstractmethod
    def run(
        self,
    ):
        """Run model."""
        generic_directory_check(self.settings.output_dir)
