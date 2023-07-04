from delft_fiat.check import (
    check_global_crs,
    check_hazard_band_names,
    check_hazard_rp_iden,
    check_hazard_subsets,
    check_srs,
)
from delft_fiat.gis import grid
from delft_fiat.gis.crs import get_srs_repr
from delft_fiat.io import open_csv, open_grid
from delft_fiat.log import spawn_logger
from delft_fiat.models.calc import calc_rp_coef
from delft_fiat.util import deter_dec

from abc import ABCMeta, abstractmethod
from osgeo import osr

logger = spawn_logger("fiat.model")


class BaseModel(metaclass=ABCMeta):
    def __init__(
        self,
        cfg: "ConfigReader",
    ):
        """ 
        BaseModel class to be used for all models in Delft-FIAT

        Parameters
        ----------
        cfg : ConfigReader
            Configuration reader object
        """

        # Set the configuration reader
        self._cfg = cfg
        logger.info(f"Using settings from '{self._cfg.filepath}'")

        # Initialize the model spatial reference
        self.srs = None
        self._exposure_data = None
        self._exposure_geoms = None
        self._exposure_grid = None
        self._hazard_grid = None
        self._vulnerability_data = None
        self._vul_step_size = 0.01
        self._rounding = 2
        self._cfg["vulnerability.round"] = self._rounding
        self._outhandler = None
        self._keep_temp = False
        self._out_meta = {}

        # Read the configuration
        self._set_model_srs()
        self._read_hazard_grid()
        self._read_vulnerability_data()

        # Check if the user wants to keep the temporary files
        if "global.keep_temp_files" in self._cfg:
            self._keep_temp = self._cfg.get("global.keep_temp_files")

    @abstractmethod
    def __del__(self):
        """Destructor for the BaseModel class"""
        self.srs = None

    def __repr__(self):
        return f"<{self.__class__.__name__} object at {id(self):#018x}>"

    @abstractmethod
    def _clean_up(self):
        raise NotImplementedError("clean_up is not implemented yet")

    def _read_hazard_grid(self):
        """Read the hazard grid"""

        # Read the hazard grid
        path = self._cfg.get("hazard.file")
        logger.info(f"Reading hazard data ('{path.name}')")

        # Generate the kwargs in case of a multiband raster
        kw = self._cfg.generate_kwargs("hazard.multiband")
        data = open_grid(path, **kw)
        
        # Check the hazard subsets 
        logger.info("Executing hazard checks...")

        # check for subsets
        check_hazard_subsets(
            data.subset_dict,
            path,
        )

        # Reproject the hazard grid if needed
        if not check_srs(self.srs, data.get_srs(), path.name):
            logger.warning(
                f"Spatial reference of '{path.name}' ('{get_srs_repr(data.get_srs())}') \
does not match the model spatial reference ('{get_srs_repr(self.srs)}')"
            )
            logger.info(f"Reprojecting '{path.name}' to '{get_srs_repr(self.srs)}'")
            _resalg = 0
            if "hazard.resampling_method" in self._cfg:
                _resalg = self._cfg.get("hazard.resampling_method")
            data = grid.reproject(data, self.srs.ExportToWkt(), _resalg)

        # check risk return periods
        if self._cfg["hazard.risk"]:
            rp = check_hazard_rp_iden(
                data.get_band_names(),
                self._cfg.get("hazard.return_periods"),
                path,
            )
            self._cfg["hazard.return_periods"] = rp
            # Directly calculate the coefficients
            rp_coef = calc_rp_coef(rp)
            self._cfg["hazard.rp_coefficients"] = rp_coef

        ## Information for output
        ns = check_hazard_band_names(
            data.deter_band_names(),
            self._cfg.get("hazard.risk"),
            self._cfg.get("hazard.return_periods"),
            data.count,
        )
        self._cfg["hazard.band_names"] = ns

        ## When all is done, add it
        self._hazard_grid = data

    def _read_vulnerability_data(self):
        """Read the vulnerability data"""

        # Read the vulnerability data
        path = self._cfg.get("vulnerability.file")
        logger.info(f"Reading vulnerability curves ('{path.name}')")
        index = "water depth"
        if "vulnerability.index" in self._cfg:
            index = self._cfg.get("vulnerability.index")
        data = open_csv(str(path), index=index)

        # Check the vulnerability subsets
        logger.info("Executing vulnerability checks...")

        # Upscale the data if needed
        if "vulnerability.step_size" in self._cfg:
            self._vul_step_size = self._cfg.get("vulnerability.step_size")
            self._rounding = deter_dec(self._vul_step_size)
            self._cfg["vulnerability.round"] = self._rounding

        logger.info(
            f"Upscaling vulnerability curves, \
using a step size of: {self._vul_step_size}"
        )
        data.upscale(self._vul_step_size, inplace=True)

        # When all is done, add the vulnerability data
        self._vulnerability_data = data

    def _set_model_srs(self):
        """Set the model spatial reference"""

        # Get the spatial reference from the configuration
        _srs = self._cfg.get("global.crs")
        path = self._cfg.get("hazard.file")

        # Check if the user has set the spatial reference
        if _srs is not None:
            self.srs = osr.SpatialReference()
            self.srs.SetFromUserInput(_srs)
        else:
            ## Inferring by 'sniffing'
            kw = self._cfg.generate_kwargs("hazard.multiband")

            gm = open_grid(
                str(path),
                **kw,
            )

            _srs = gm.get_srs()
            if _srs is None:
                if "hazard.crs" in self._cfg:
                    _srs = osr.SpatialReference()
                    _srs.SetFromUserInput(self._cfg.get("hazard.crs"))
            self.srs = _srs

        ## Simple check to see if it's not None
        check_global_crs(
            self.srs,
            self._cfg.filepath.name,
            path.name,
        )

        logger.info(f"Model srs set to: '{get_srs_repr(self.srs)}'")

    @abstractmethod
    def run():
        raise NotImplementedError("run is not implemented yet")
