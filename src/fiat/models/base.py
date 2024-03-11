"""Base model of FIAT."""

from abc import ABCMeta, abstractmethod
from multiprocessing import Manager
from os import cpu_count

from osgeo import osr

from fiat.check import (
    check_duplicate_columns,
    check_global_crs,
    check_hazard_band_names,
    check_hazard_rp_iden,
    check_hazard_subsets,
    check_internal_srs,
    check_vs_srs,
)
from fiat.gis import grid
from fiat.gis.crs import get_srs_repr
from fiat.io import open_csv, open_grid
from fiat.log import spawn_logger
from fiat.models.calc import calc_rp_coef
from fiat.util import NEED_IMPLEMENTED, deter_dec

logger = spawn_logger("fiat.model")


class BaseModel(metaclass=ABCMeta):
    """_summary_."""

    def __init__(
        self,
        cfg: object,
    ):
        """_summary_."""
        self.cfg = cfg
        logger.info(f"Using settings from '{self.cfg.filepath}'")

        ## Declarations
        # Model data
        self.srs = None
        self.exposure_data = None
        self.exposure_geoms = None
        self.exposure_grid = None
        self.hazard_grid = None
        self.vulnerability_data = None
        # Vulnerability data
        self._vul_step_size = 0.01
        self._rounding = 2
        self.cfg["vulnerability.round"] = self._rounding
        # Temporay files
        self._keep_temp = False
        # Threading stuff
        self._mp_manager = Manager()
        self.max_threads = 1
        self.nthreads = 1
        self.chunk = None
        self.chunks = []
        self.nchunk = 0

        self._set_max_threads()
        self._set_model_srs()
        self.read_hazard_grid()
        self.read_vulnerability_data()

        if "global.keep_temp_files" in self.cfg:
            self._keep_temp = self.cfg.get("global.keep_temp_files")

    @abstractmethod
    def __del__(self):
        self.srs = None
        self._mp_manager.shutdown()

    def __repr__(self):
        return f"<{self.__class__.__name__} object at {id(self):#018x}>"

    @abstractmethod
    def _clean_up(self):
        raise NotImplementedError(NEED_IMPLEMENTED)

    def _set_model_srs(self):
        """_summary_."""
        _srs = self.cfg.get("global.crs")
        path = self.cfg.get("hazard.file")
        if _srs is not None:
            self.srs = osr.SpatialReference()
            self.srs.SetFromUserInput(_srs)
        else:
            # Inferring by 'sniffing'
            kw = self.cfg.generate_kwargs("hazard.settings")

            gm = open_grid(
                str(path),
                **kw,
            )

            _srs = gm.get_srs()
            if _srs is None:
                if "hazard.crs" in self.cfg:
                    _srs = osr.SpatialReference()
                    _srs.SetFromUserInput(self.cfg.get("hazard.crs"))
            self.srs = _srs

        # Simple check to see if it's not None
        check_global_crs(
            self.srs,
            self.cfg.filepath.name,
            path.name,
        )
        # Set crs for later use
        self.cfg["global.crs"] = get_srs_repr(self.srs)

        logger.info(f"Model srs set to: '{get_srs_repr(self.srs)}'")
        # Clean up
        gm = None

    @abstractmethod
    def _set_num_threads(
        self,
    ):
        """_summary_."""
        raise NotImplementedError(NEED_IMPLEMENTED)

    @abstractmethod
    def _setup_output_files(
        self,
    ):
        """_summary_."""
        raise NotImplementedError(NEED_IMPLEMENTED)

    def read_hazard_grid(self):
        """_summary_."""
        path = self.cfg.get("hazard.file")
        logger.info(f"Reading hazard data ('{path.name}')")
        # Set the extra arguments from the settings file
        kw = {}
        kw.update(
            self.cfg.generate_kwargs("hazard.settings"),
        )
        kw.update(
            self.cfg.generate_kwargs("global.grid"),
        )
        data = open_grid(path, **kw)
        ## checks
        logger.info("Executing hazard checks...")

        # check for subsets
        check_hazard_subsets(
            data.subset_dict,
            path,
        )

        # check the internal srs of the file
        _int_srs = check_internal_srs(
            data.get_srs(),
            path.name,
        )
        if _int_srs is not None:
            logger.info(
                f"Setting spatial reference of '{path.name}' \
from '{self.cfg.filepath.name}' ('{get_srs_repr(_int_srs)}')"
            )
            raise ValueError("")

        # check if file srs is the same as the model srs
        if not check_vs_srs(self.srs, data.get_srs()):
            logger.warning(
                f"Spatial reference of '{path.name}' \
('{get_srs_repr(data.get_srs())}') does not match the \
model spatial reference ('{get_srs_repr(self.srs)}')"
            )
            logger.info(f"Reprojecting '{path.name}' to '{get_srs_repr(self.srs)}'")
            _resalg = 0
            if "hazard.resampling_method" in self.cfg:
                _resalg = self.cfg.get("hazard.resampling_method")
            data = grid.reproject(data, self.srs.ExportToWkt(), _resalg)

        # check risk return periods
        if self.cfg["hazard.risk"]:
            rp = check_hazard_rp_iden(
                data.get_band_names(),
                self.cfg.get("hazard.return_periods"),
                path,
            )
            self.cfg["hazard.return_periods"] = rp
            # Directly calculate the coefficients
            rp_coef = calc_rp_coef(rp)
            self.cfg["hazard.rp_coefficients"] = rp_coef

        # Information for output
        ns = check_hazard_band_names(
            data.deter_band_names(),
            self.cfg.get("hazard.risk"),
            self.cfg.get("hazard.return_periods"),
            data.count,
        )
        self.cfg["hazard.band_names"] = ns

        # When all is done, add it
        self.hazard_grid = data

    def read_vulnerability_data(self):
        """_summary_."""
        path = self.cfg.get("vulnerability.file")
        logger.info(f"Reading vulnerability curves ('{path.name}')")

        # Setting the keyword arguments from settings file
        kw = {"index": "water depth"}
        kw.update(
            self.cfg.generate_kwargs("vulnerability.settings"),
        )
        data = open_csv(str(path), **kw)
        ## checks
        logger.info("Executing vulnerability checks...")

        # Column check
        check_duplicate_columns(data._dup_cols)

        # upscale the data (can be done after the checks)
        if "vulnerability.step_size" in self.cfg:
            self._vul_step_size = self.cfg.get("vulnerability.step_size")
            self._rounding = deter_dec(self._vul_step_size)
            self.cfg["vulnerability.round"] = self._rounding

        logger.info(
            f"Upscaling vulnerability curves, \
using a step size of: {self._vul_step_size}"
        )
        data.upscale(self._vul_step_size, inplace=True)
        # When all is done, add it
        self.vulnerability_data = data

    def _set_max_threads(self):
        """_summary_."""
        self.max_threads = cpu_count()
        _max_threads = self.cfg.get("global.threads")
        if _max_threads is not None:
            if _max_threads > self.max_threads:
                logger.warning(
                    f"Given number of threads ('{_max_threads}') \
exceeds machine thread count ('{self.max_threads}')"
                )
            self.max_threads = min(self.max_threads, _max_threads)

        logger.info(f"Maximum number of threads: {self.max_threads}")

    @abstractmethod
    def run(
        self,
    ):
        """_summary_."""
        raise NotImplementedError(NEED_IMPLEMENTED)
