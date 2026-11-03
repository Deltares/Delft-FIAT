"""Settings for the variables of the input datasets."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from fiat.util import CATEGORIZED, DEFAULT, VALUES

__all__ = [
    "ExposureGridVariable",
    "HazardVariable",
    "VulnerabilityVariable",
]

EXPOSURE_TYPES = [DEFAULT, CATEGORIZED, VALUES]


class Variable(BaseModel):
    """Base settings for a variable of an input dataset."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        default=...,
        description="Name of the variable in the dataset.",
    )


class ExposureGridVariable(Variable):
    """Settings for a variable (layer) of the exposure grid dataset."""

    type: str = Field(
        default=...,
        description="The exposure type: 'default' or 'categorized' for a layer, \
'values' for a category-value variable.",
    )

    vulnerability: str | list[str] | None = Field(
        default=None,
        description="The vulnerability dataset(s) linked to this variable.",
    )

    fn_curve: str | int | None = Field(
        default=None,
        description="The curve id looked up in the linked vulnerability dataset(s).",
    )

    values: list[str] | None = Field(
        default=None,
        description="The category-value variables of a categorized layer.",
    )

    value: float | None = Field(
        default=None,
        description="Constant value of a uniform layer that is not in the file.",
    )

    # Validator(s)
    @field_validator("type", mode="after")
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


class HazardVariable(Variable):
    """Settings for a variable (band) of the hazard dataset."""

    type: str = Field(
        default=...,
        description="The hazard type, e.g. 'water_depth' or 'duration'.",
    )

    rp: float | None = Field(
        default=None,
        description="The return period of the hazard band (required for risk).",
    )

    value: float | None = Field(
        default=None,
        description="Constant value of a uniform layer that is not in the file.",
    )


class VulnerabilityVariable(Variable):
    """Settings for a variable (dataset) of the vulnerability file."""

    method: str = Field(
        default=...,
        description="The calculation method of the dataset, e.g. 'flood.depth'.",
    )

    types: dict[str, str] = Field(
        default=...,
        description="The hazard type per index dimension of the dataset.",
    )
