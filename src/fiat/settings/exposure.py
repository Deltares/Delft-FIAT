"""Settings for the exposure (file(s))."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from fiat.settings.file import InputFileModel

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
