from delft_fiat.io import open_csv, open_geom, open_grid

from abc import ABCMeta, abstractmethod
from osgeo import osr


class BaseModel(metaclass=ABCMeta):
    def __init__(
        self,
        cfg: "ConfigReader",
    ):
        """_summary_"""

        self._cfg = cfg

        self.srs = osr.SpatialReference()
        self.srs.SetFromUserInput(self._cfg.get("global.crs"))

        # Declarations
        self.exposure_data = None
        self.exposure_geoms = None
        self.exposure_grid = None
        self.hazard_grid = None
        self.risk_grid = None
        self.vulnerability_data = None
        self._outhandler = None

        self.read_hazard_grid()
        self.read_vulnerability_data()

    @abstractmethod
    def __del__(self):
        self.srs = None
        pass

    def __repr__(self):
        return f"<{self.__class__.__name__} object at {id(self):#018x}>"

    def read_hazard_grid(self):
        data = open_grid(self._cfg.get_path("hazard.grid_file"))
        ## checks

        self.hazard_grid = data

    def read_vulnerability_data(self):
        data = open_csv(self._cfg.get_path("vulnerability.dbase_file"))
        ## checks

        self.vulnerability_data = data

    def get_damage_curve(
        self,
        oid: str,
    ) -> dict:
        dc = self.vul_data[oid]
        return dc

    def get_exposure(
        self,
        bla,
    ):
        pass

    def get_objects():
        pass

    @abstractmethod
    def run():
        pass
