from pathlib import Path
from typing import List, Tuple

from delft_fiat.io import open_csv, open_grid
from delft_fiat.models_refactor.exposure_models.base_model import BaseModel
from delft_fiat.models_refactor.types import CSV, GridSource


class HazardImpactModel(object):
    def __init__(self, config):
        self._hazard_grid: GridSource
        self._vulnerability: CSV
        self._exposure_model: BaseModel

        self.hazard_grid = config.get_path("hazard.grid_file")
        self.hazard_ref: str = config.get("hazard.crs")
        self.vulnerability = (
            config.get_path("vulnerability.dbase_file"),
            config.get("vulnerability.spacing"),
        )

    def _read_hazard_grid(self, path: str) -> GridSource:
        try:
            return open_grid(path)
        except IOError as ioerr:
            # write to log
            raise IOError("Error: File does not appear to exist.") from ioerr

    def _read_vulnerability(self, path: str) -> CSV:
        try:
            return open_csv(path, large=False)
        except IOError as ioerr:
            # write to log
            raise IOError("Error: File does not appear to exist.") from ioerr

    @property
    def hazard_grid(self):
        return self._hazard_grid

    @hazard_grid.setter
    def hazard_grid(self, path: str):
        self._hazard_grid = self._read_hazard_grid(path)

    @property
    def vulnerability(self) -> CSV:
        return self._vulnerability

    @vulnerability.setter
    def vulnerability(self, params: Tuple[str, str]):
        path, spacing = params
        self._vulnerability = self._read_vulnerability(path)
        self._vulnerability.upscale(float(spacing))

    @property
    def exposure_model(self) -> BaseModel:
        return self._exposure_model

    @exposure_model.setter
    def exposure_model(self, exposure_map: BaseModel) -> None:
        self._exposure_model = exposure_map

    @property
    def return_period_count(self) -> int:
        return self._hazard_grid.src.RasterCount

    def simulate_impact(self, exposure_map: BaseModel, output_path: Path):
        self.exposure_model = exposure_map
        period_count: int = self.return_period_count

        for period in range(period_count):
            self._exposure_model.calc_hazard_impact(
                hazard=self._hazard_grid.src,
                hazard_ref=self.hazard_ref,
                band_id=period + 1,
                vulnerabilities=self._vulnerability,
                output_path=output_path
            )
        # This can be parallelized. Each period can be ran independently

    def write(self, result):
        pass
