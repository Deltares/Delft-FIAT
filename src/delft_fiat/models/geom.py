from delft_fiat.models.base import BaseModel

import time
from osgeo import gdal, ogr


class GeomModel(BaseModel):
    def __init__(
        self,
        cfg: "ConfigReader",
    ):
        super().__init__(cfg)
        pass
