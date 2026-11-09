"""Settings for the variables of the input datasets."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

__all__ = ["Variable"]


class Variable(BaseModel):
    """Base settings for a variable of an input dataset."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        default=...,
        description="Name of the variable in the dataset.",
    )
