from delft_fiat.io import open_csv, open_geom

from abc import ABCMeta, abstractmethod


class BaseModel(metaclass=ABCMeta):
    def __init__(self, cfg: "ConfigReader"):
        # Declarations
        self.hazard_data = None
        self.exposure_geoms = None
        self.exposure_base = None
        self.vul_data = None
        self._cfg = cfg

    def read_damage_files():
        pass

    def read_hazard_files():
        pass

    def read_exposure_files(self):
        return open_geom()

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
