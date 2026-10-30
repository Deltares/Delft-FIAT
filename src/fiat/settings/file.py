"""Base model for (input) files."""

from pathlib import Path

from pydantic import (
    BaseModel,
    Field,
    SerializationInfo,
    ValidationInfo,
    field_serializer,
    field_validator,
)

from fiat.settings.util import _relpath
from fiat.util import FILE, OUTPUT, generic_file_check

__all__ = ["InputFileModel", "OutputFileModel"]


class FileContext(BaseModel):
    """Context for in- and output files."""

    config_dir: Path | None = Field(
        default=None,
        description="Path of the config file directory.",
    )

    output_dir: Path | None = Field(
        default=None,
        description="Path of the directory of the model output.",
    )


DEFAULT_CONTEXT = FileContext(config_dir=Path.cwd(), output_dir=Path.cwd() / OUTPUT)


class InputFileModel(BaseModel):
    """Input file base model."""

    file: Path = Field(
        default=...,
        description="Path to the input file.",
    )

    @field_validator(FILE, mode="after")
    @classmethod
    def validate_file(cls, value: Path, info: ValidationInfo):
        """Make the path absolute with the config file directory."""
        context: FileContext = info.context or DEFAULT_CONTEXT
        return generic_file_check(file=value, root=context.config_dir)

    @field_serializer(FILE)
    def serialize_file(self, value: Path, info: SerializationInfo) -> str:
        """Make the paths relative to the config file."""
        context: FileContext = info.context or DEFAULT_CONTEXT
        return _relpath(value=value, root=context.config_dir)


class OutputFileModel(BaseModel):
    """Output file base model."""

    file: Path = Field(
        default=...,
        description="Path to the output file.",
    )

    @field_validator(FILE, mode="after")
    @classmethod
    def validate_file(cls, value: Path, info: ValidationInfo):
        """Make the path absolute with the output file directory."""
        context: FileContext = info.context or DEFAULT_CONTEXT
        return generic_file_check(file=value, root=context.output_dir, error=False)

    @field_serializer(FILE)
    def serialize_file(self, value: Path, info: SerializationInfo) -> str:
        """Make the paths relative to the output file directory."""
        context: FileContext = info.context or DEFAULT_CONTEXT
        return _relpath(value=value, root=context.output_dir)
