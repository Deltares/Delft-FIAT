"""Settings for the hazard (file)."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from fiat.settings.file import InputFileModel
from fiat.settings.variables import Variable

__all__ = ["Hazard"]


class HazardSettings(BaseModel):
    """Settings for reading the hazard data."""

    model_config = ConfigDict(extra="forbid")

    crs: str | None = Field(
        default=None,
        description="Spatial reference system of the file.",
    )


class HazardVariable(Variable):
    """Settings for a variable (band) of the hazard dataset."""

    rp: float | None = Field(
        default=None,
        description="The return period of the hazard band (required for risk).",
    )

    type: str = Field(
        default=...,
        description="The hazard type, e.g. 'water_depth' or 'duration'.",
    )

    value: float | None = Field(
        default=None,
        description="Constant value of a uniform layer that is not in the file.",
    )


class Hazard(InputFileModel):
    """Hazard settings for the FIAT model."""

    resalg: str = Field(
        default="nearest",
        description="Resampling method when reprojecting.",
    )

    settings: HazardSettings = Field(
        default=HazardSettings(),
        description="Settings for reading the hazard data.",
    )

    variables: list[HazardVariable] = Field(
        default=...,
        min_length=1,
        description="Settings per hazard variable (band).",
    )
