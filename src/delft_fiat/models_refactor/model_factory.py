from abc import ABCMeta, abstractmethod
from typing import List

from osgeo import osr

from delft_fiat.models_refactor.model_types import (
    CSV,
    DamageType,
    ExposureMap,
    GridSource,
)


class ModelFactory(metaclass=ABCMeta):
    """
    Parameters
    ----------
    metaclass : _type_, optional
        _description_, by default ABCMeta
    """

    def __init__(self, path: str) -> None:
        """_summary_

        Parameters
        ----------
        foo : any
            _description_
        """

        self.srs = osr.SpatialReference()

        self._exposure_map: ExposureMap
        self.exposure_map = path

    @abstractmethod
    def __del__(self):
        self.srs = None
        ...

    def __repr__(self):
        return f"<{self.__class__.__name__} object at {id(self):#018x}>"

    @abstractmethod
    def _read_exposure_map(self, path: str) -> ExposureMap:
        raise NotImplementedError

    @property
    def exposure_map(self) -> ExposureMap:
        return self._exposure_map

    @exposure_map.setter
    def exposure_map(self, path: str) -> None:
        self._exposure_map = self._read_exposure_map(path)

    @abstractmethod
    def run(
        self,
        hazard_grid: GridSource,
        exposure: CSV,
        damage_categories: List[DamageType],
        vulnerabilities: CSV,
    ):
        raise NotImplementedError
