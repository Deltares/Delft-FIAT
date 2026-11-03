"""Settings for the variables of the input datasets."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from fiat.driver.netcdf.reader import VariableSpec
from fiat.util import CATEGORIZED, DEFAULT, NAME, VALUE

__all__ = [
    "ExposureGridVariable",
    "HazardVariable",
    "VulnerabilityVariable",
    "variable_specs",
]

EXPOSURE_TYPES = [DEFAULT, CATEGORIZED]


class Variable(BaseModel):
    """Base settings for a variable of an input dataset."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        default=...,
        description="Name of the variable in the dataset.",
    )

    def spec(self) -> VariableSpec:
        """Return the variable specification (attribute overrides and value)."""
        attrs = self.model_dump(exclude={NAME, VALUE}, exclude_none=True)
        return VariableSpec(attrs=attrs, value=getattr(self, VALUE, None))


class ExposureGridVariable(Variable):
    """Settings for a variable (layer) of the exposure grid dataset."""

    type: str | None = Field(
        default=None,
        description="The exposure type, either 'default' or 'categorized'.",
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
    def validate_type(cls, value: str | None):
        """Validate the exposure type."""
        if value is not None and value not in EXPOSURE_TYPES:
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


class HazardVariable(Variable):
    """Settings for a variable (band) of the hazard dataset."""

    type: str | None = Field(
        default=None,
        description="The hazard type, e.g. 'water_depth' or 'duration'.",
    )

    rp: float | None = Field(
        default=None,
        description="The return period of the hazard band.",
    )

    value: float | None = Field(
        default=None,
        description="Constant value of a uniform layer that is not in the file.",
    )


class VulnerabilityVariable(Variable):
    """Settings for a variable (dataset) of the vulnerability file."""

    method: str | None = Field(
        default=None,
        description="The calculation method of the dataset, e.g. 'flood.depth'.",
    )

    types: dict[str, str] | None = Field(
        default=None,
        description="The hazard type per index dimension of the dataset.",
    )


def variable_specs(variables: list[Variable]) -> dict[str, VariableSpec]:
    """Create the variable specifications from the variables settings.

    Parameters
    ----------
    variables : list[Variable]
        The variables settings.

    Returns
    -------
    dict[str, VariableSpec]
        The specification per variable name.
    """
    return {item.name: item.spec() for item in variables}
