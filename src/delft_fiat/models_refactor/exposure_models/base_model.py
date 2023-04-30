from abc import ABCMeta, abstractmethod
from typing import Optional

from osgeo import gdal, osr

from delft_fiat.models_refactor.types import CSV, ExposureMap


class BaseModel(metaclass=ABCMeta):
    """
    Parameters
    ----------
    metaclass : _type_, optional
        _description_, by default ABCMeta
    """

    def __init__(self, path: str, crs: str) -> None:
        """_summary_

        Parameters
        ----------
        foo : any
            _description_
        """

        self.srs = osr.SpatialReference()
        self.srs.SetFromUserInput(crs)

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
    def calc_hazard_impact(
        self,
        hazard: gdal.Dataset,
        hazard_ref: str,
        band_id: int,
        vulnerabilities: Optional[CSV] = None,
    ):
        raise NotImplementedError
