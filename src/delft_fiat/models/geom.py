from delft_fiat.gis import overlay, geom
from delft_fiat.io import open_csv, open_geom
from delft_fiat.models.base import BaseModel
from delft_fiat.models.calc import *

import time
from concurrent.futures import ProcessPoolExecutor
from osgeo import gdal, ogr


class GeomModel(BaseModel):
    def __init__(
        self,
        cfg: "ConfigReader",
    ):
        super().__init__(cfg)

        self._geoms = True
        self.read_exposure_data()
        if self._geoms:
            self.read_exposure_geoms()

    def __del__(self):
        BaseModel.__del__(self)

    def read_exposure_data(self):
        data = open_csv(self._cfg.get("exposure.dbase_file"))
        ##checks
        self.exposure_data = data

    def read_exposure_geoms(self):
        data = open_geom(self._cfg.get_path("exposure.geom_file"))
        ##checks
        if not self.srs.IsSame(data.get_srs()):
            data = geom.reproject(data, data.get_srs().ExportToWkt())
        self.exposure_geoms = data

    def run(self):
        for ft in self.exposure_geoms:
            pass
