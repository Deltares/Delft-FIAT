from typing import Type, Union

from delft_fiat.models_refactor.exposure_models.base_model import BaseModel
from delft_fiat.models_refactor.exposure_models.coordinate_model import CoordinateModel
from delft_fiat.models_refactor.exposure_models.raster_model import RasterModel
from delft_fiat.models_refactor.exposure_models.vector_model import VectorModel
from delft_fiat.models_refactor.types import ExposureConfig, ModelType


class ModelFactory:
    def __init__(self):
        pass

    @classmethod
    def issue(
        cls, model_type: ModelType, config: ExposureConfig, crs: str
    ) -> Union[BaseModel, None]:
        match model_type:
            case "vector":
                return VectorModel(config, crs)
            case "raster":
                return RasterModel(config, crs)
            case "coordinate":
                return CoordinateModel(config, crs)
