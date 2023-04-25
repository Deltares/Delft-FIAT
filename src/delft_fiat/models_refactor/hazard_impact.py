from typing import List

from delft_fiat.models_refactor.model_factory import ModelFactory
from delft_fiat.models_refactor.model_types import *


class HazardImpactModel(object):
    def __init__(self, cfg):
        self._hazard_grid: GridSource
        self._exposure: CSV
        self._vulnerability: CSV
        self._exposure_geom: ExposureMap
        self._damage_categories: List[DamageType]

        self.hazard_grid = cfg["hazard_grid"]
        self.exposure = cfg["exposure"]
        self.vulnerability = cfg["vulnerability"]

    def _read_hazard_grid(self, path: str):
        ...

    def _read_exposure(self, path: str):
        ...

    def _read_vulnerability(self, path: str):
        ...

    @property
    def hazard_grid(self):
        return self._hazard_grid

    @hazard_grid.setter
    def hazard_grid(self, path: str):
        self._hazard_grid = self._read_hazard_grid(path)

    @property
    def exposure(self):
        return self._exposure

    @exposure.setter
    def exposure(self, path: str):
        self._exposure = self._read_exposure(path)
        headers: List[str] = self._exposure.headers
        self._damage_categories = self._get_damage_categories(headers)

    @property
    def vulnerability(self):
        return self._vulnerability

    @vulnerability.setter
    def vulnerability(self, path: str, df: float):
        self._vulnerability = self._read_vulnerability(path)
        self._vulnerability.upscale(df)

    @property
    def exposure_geom(self):
        return self._exposure_geom

    @exposure_geom.setter
    def exposure_geom(self, exposure_map: ModelFactory):
        self._exposure_geom = exposure_map

    def _get_damage_categories(self, headers: List[str]):
        return [
            (header, header.replace("Damage Function: ", "Max Potential Damage: "))
            for header in headers
            if header.startswith("Damage Function:")
        ]

    def simulate_impact(self, exposure_map: ModelFactory):
        self.exposure_geom = exposure_map

        self.exposure_geom.run(
            self._hazard_grid,
            self._exposure,
            self._damage_categories,
            self._vulnerability,
        )

    def write(result: any):
        ...

    def write(result: any):
        ...
