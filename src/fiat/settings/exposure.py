"""Settings for the exposure (file(s))."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from fiat.method.util import ZONAL_CODES
from fiat.settings.file import InputFileModel
from fiat.util import AREA__METHODS

__all__ = ["ExposureGeometry", "ExposureGrid"]


class ExposureGeometrySettings(BaseModel):
    """Settings for reading the exposure geometry data."""

    model_config = ConfigDict(extra="forbid")

    crs: str | None = Field(
        default=None,
        description="Spatial reference system of the file.",
    )


class ExposureGeometry(InputFileModel):
    """Exposure geometry settings for the FIAT model."""

    area_method: str = Field(
        default="centroid",
        description="The method of extracting hazard values \
based on the exposure geometry.",
    )

    impact_type: list[str] = Field(
        default=["damage"],
        description="The impact types to be run for this exposure data.",
    )

    settings: ExposureGeometrySettings = Field(
        default=ExposureGeometrySettings(),
        description="Settings for reading the exposure geometry data.",
    )

    zonal_method: str = Field(
        default="mean",
        description="The zonal statistics method. Only really applicable \
if `area_method` is set to 'area'.",
    )

    # Validator(s)
    @field_validator("area_method", mode="after")
    @classmethod
    def validate_area_method(cls, value: str):
        """Validate the zonal method setting."""
        if value not in AREA__METHODS:
            raise ValueError(
                f"Area method invalid: {value}, \chose from {AREA__METHODS}",
            )
        return value

    @field_validator("zonal_method", mode="after")
    @classmethod
    def validate_zonal_method(cls, value: str):
        """Validate the zonal method setting."""
        if value not in ZONAL_CODES:
            raise ValueError(
                f"Zonal method invalid: {value}, \chose from {list(ZONAL_CODES)}",
            )
        return value


class ExposureGridSettings(BaseModel):
    """Settings for reading the exposure grid data."""

    model_config = ConfigDict(extra="forbid")

    crs: str | None = Field(
        default=None,
        description="Spatial reference system of the file.",
    )


class ExposureGrid(InputFileModel):
    """Exposure grid settings for the FIAT model."""

    resalg: str = Field(
        default="nearest",
        description="Resampling method when reprojecting.",
    )

    settings: ExposureGridSettings | None = Field(
        default=None,
        description="Settings for reading the exposure grid data.",
    )
