"""Settings for the hazard (file)."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from fiat.settings.file import InputFileModel
from fiat.settings.variables import HazardVariable

__all__ = ["Hazard"]


class HazardSettings(BaseModel):
    """Settings for reading the hazard data."""

    model_config = ConfigDict(extra="forbid")

    crs: str | None = Field(
        default=None,
        description="Spatial reference system of the file.",
    )


class Hazard(InputFileModel):
    """Hazard settings for the FIAT model."""

    resalg: str = Field(
        default="nearest",
        description="Resampling method when reprojecting.",
    )

    rp: list[float] | None = Field(
        default=None,
        description="Return periods for the hazard values.",
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
