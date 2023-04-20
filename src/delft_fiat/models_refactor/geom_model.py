from typing import TypeAlias, Union

from delft_fiat.gis import geom, overlay
from delft_fiat.io import CSVLarge, CSVSmall, GeomSource, GridSource, open_geom
from delft_fiat.models.base import BaseModel
from delft_fiat.models.calc import *

ExposureMap: TypeAlias = Union[GeomSource, GridSource]
CSV: TypeAlias = Union[CSVLarge, CSVSmall]


class GeomModel(BaseModel):
    _method = {
        "area": overlay.clip,
        "average": overlay.pin,
    }

    def __init__(self, path: str) -> None:
        super().__init__(path)

    def __del__(self) -> None:
        BaseModel.__del__(self)

    def _read_exposure_map(self, path: str) -> ExposureMap:
        geom_exposure: GeomSource = open_geom(path)
        ##checks
        geom_srs = geom_exposure.get_srs()
        if not self.srs.IsSame(geom_srs):
            geom_exposure = geom.reproject(geom_exposure, geom_srs.ExportToWkt())
        return geom_exposure

    def run(self, hazard_grid: GridSource, exposure: CSV, vulnerability: CSV):
        for ft in self.exposure_geoms:
            pass
