"""Settings for the exposure (file(s))."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from fiat.method.util import ZONAL_CODES
from fiat.settings.file import InputFileModel
from fiat.settings.variables import Variable
from fiat.util import (
    AREA__METHOD,
    AREA__METHODS,
    CATEGORIZED,
    DEFAULT,
    IMPACT__TYPE,
    TYPE,
    VALUES,
    ZONAL__METHOD,
)

__all__ = ["ExposureGeometry", "ExposureGrid"]

EXPOSURE_TYPES = [DEFAULT, CATEGORIZED, VALUES]


class ExposureGeometrySettings(BaseModel):
    """Settings for reading the exposure geometry data."""

    model_config = ConfigDict(extra="forbid")

    crs: str | None = Field(
        default=None,
        description="Spatial reference system of the file.",
    )


class ExposureGeometryVariable(BaseModel):
    """Exposure geometry file variables."""

    area_method: str = Field(
        default="centroid",
        description="The method of extracting hazard values \
based on the exposure geometry.",
    )

    impact_type: list[str] = Field(
        default=["damage"],
        description="The impact types to be run for this exposure data.",
    )

    vulnerability: str = Field(
        default=...,
        description="The vulnerability dataset (variable) to use from the \
vulnerability netcdf dataset.",
    )

    zonal_method: str = Field(
        default="mean",
        description="The zonal statistics method. Only really applicable \
if `area_method` is set to 'area'.",
    )

    # Validator(s)
    @field_validator(AREA__METHOD, mode="after")
    @classmethod
    def validate_area_method(cls, value: str):
        """Validate the zonal method setting."""
        if value not in AREA__METHODS:
            raise ValueError(
                f"Area method invalid: {value}, chose from {AREA__METHODS}",
            )
        return value

    @field_validator(IMPACT__TYPE, mode="before")
    @classmethod
    def ensure_impact_type_list(cls, value: str | list[str]):
        """Ensure impact type list typing."""
        if not isinstance(value, list):
            value = [value]
        return value

    @field_validator(ZONAL__METHOD, mode="after")
    @classmethod
    def validate_zonal_method(cls, value: str):
        """Validate the zonal method setting."""
        if value not in ZONAL_CODES:
            raise ValueError(
                f"Zonal method invalid: {value}, chose from {list(ZONAL_CODES)}",
            )
        return value


class ExposureGeometry(InputFileModel):
    """Exposure geometry settings for the FIAT model."""

    settings: ExposureGeometrySettings = Field(
        default=ExposureGeometrySettings(),
        description="Settings for reading the exposure geometry data.",
    )

    variables: ExposureGeometryVariable = Field(
        default=...,
        description="Settings per exposure file.",
    )


class ExposureGridSettings(BaseModel):
    """Settings for reading the exposure grid data."""

    model_config = ConfigDict(extra="forbid")

    crs: str | None = Field(
        default=None,
        description="Spatial reference system of the file.",
    )


class ExposureGridVariable(Variable):
    """Settings for a variable (layer) of the exposure grid dataset."""

    fn_curve: str | int | None = Field(
        default=None,
        description="The curve id looked up in the linked vulnerability dataset(s).",
    )

    type: str = Field(
        default=...,
        description="The exposure type: 'default' or 'categorized' for a layer, \
'values' for a category-value variable.",
    )

    value: float | None = Field(
        default=None,
        description="Constant value of a uniform layer that is not in the file.",
    )

    values: list[str] | None = Field(
        default=None,
        description="The category-value variables of a categorized layer.",
    )

    vulnerability: str | list[str] | None = Field(
        default=None,
        description="The vulnerability dataset(s) linked to this variable.",
    )

    # Validator(s)
    @field_validator(TYPE, mode="after")
    @classmethod
    def validate_type(cls, value: str):
        """Validate the exposure type."""
        if value not in EXPOSURE_TYPES:
            raise ValueError(
                f"Exposure type invalid: {value}, chose from {EXPOSURE_TYPES}",
            )
        return value

    @model_validator(mode="after")
    def validate_values(self):
        """Validate that values are only set on categorized layers."""
        if self.values is not None and self.type != CATEGORIZED:
            raise ValueError(
                f"'values' is only allowed for type '{CATEGORIZED}' ({self.name})"
            )
        return self

    @model_validator(mode="after")
    def validate_vulnerability(self):
        """Validate the link to the vulnerability dataset(s)."""
        if self.type == CATEGORIZED:
            if self.vulnerability is not None:
                raise ValueError(
                    f"'vulnerability' is not allowed for type '{CATEGORIZED}', set "
                    f"it on the category-value variables ({self.name})"
                )
        elif not self.vulnerability:
            raise ValueError(
                f"'vulnerability' is required for type '{self.type}' ({self.name})"
            )
        return self

    @model_validator(mode="after")
    def validate_fn_curve(self):
        """Validate that default layers have a curve id."""
        if self.type == DEFAULT and self.fn_curve is None:
            raise ValueError(
                f"'fn_curve' is required for type '{DEFAULT}' ({self.name})"
            )
        return self


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

    variables: list[ExposureGridVariable] = Field(
        default=...,
        min_length=1,
        description="Settings per exposure variable (layer).",
    )
