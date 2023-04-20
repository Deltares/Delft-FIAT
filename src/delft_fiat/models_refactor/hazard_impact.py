class HazardImpactModel(object):
    def __init__(self, cfg):
        self._hazard_grid: GridSource
        self._exposure: CSV
        self._vulnerability: CSV
        self._exposure_geom: ExposureMap

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

    @property
    def vulnerability(self):
        return self._vulnerability

    @vulnerability.setter
    def vulnerability(self, path: str):
        self._vulnerability = self._read_vulnerability(path)

    @property
    def exposure_geom(self):
        return self._exposure_geom

    @exposure_geom.setter
    def exposure_geom(self, exposure_map: ModelFactory):
        self._exposure_geom = exposure_map

    def simulate_impact(self, exposure_map: ModelFactory):
        self.exposure_geom = exposure_map

        self.exposure_geom.run(self._hazard_grid, self._exposure, self._vulnerability)

    def write(result: any):
        ...
