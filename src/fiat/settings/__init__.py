"""Settings for the FIAT model."""

import tomllib
from os import cpu_count
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    TypeAdapter,
    ValidationInfo,
    field_serializer,
    field_validator,
    model_validator,
)

from fiat.log import spawn_logger
from fiat.log.util import LogLevels
from fiat.util import (
    EXPOSURE,
    FILE,
    FLOOD_DEPTH,
    HAZARD,
    OUTPUT,
    generic_file_check,
)

from .exposure import ExposureGeometry, ExposureGrid
from .file import DEFAULT_CONTEXT, FileContext, OutputFileModel
from .hazard import Hazard
from .util import _relpath
from .vulnerability import Vulnerability

__all__ = ["GeomSettings", "GridSettings"]

logger = spawn_logger(__name__)


class ModelGeom(BaseModel):
    """Settings for the geometry based model."""

    chunk: int | None = Field(
        default=None, ge=1, description="The chunking size (number of features)."
    )


class ModelGrid(BaseModel):
    """Settings for the grid based model."""

    base: str = Field(
        default=HAZARD,
        description="Which file to take as the base in terms of transform and extend.",
    )

    chunk: list[int, int] | None = Field(
        default=None, description="The chunking size (number of rows and columns)."
    )


class ModelProjection(BaseModel):
    """Settings for the model-wide crs."""

    crs: str = Field(
        default=None, description="The model-wide coordinate reference system."
    )

    force: bool = Field(
        default=False,
        description="Force the model-wide crs on all the spatial input files.",
    )


class BaseSettings(BaseModel):
    """Settings for both geom and grid model."""

    model_config = ConfigDict(validate_default=True)

    _context: FileContext = PrivateAttr()

    # Model wide settings
    loglevel: str = Field(default="INFO", description="The logging level of FIAT.")

    method: str = Field(
        default=FLOOD_DEPTH,
        description="Method to use for the model. \
Can be either 'flood.depth' or 'flood.level'.",
    )

    output_dir: Path = Field(
        default=Path("output"),
        description="Directory to store the output of the model.",
    )

    risk: bool = Field(
        default=False,
        description="Whether to perform a risk analysis.",
    )

    threads: int = Field(
        default=1,
        ge=1,
        description="Number of threads to use for the model.",
    )

    # Model projection
    projection: ModelProjection = Field(
        default=ModelProjection(), description="The model wide projection."
    )

    # Input data
    vulnerability: Vulnerability = Field(
        default=...,
        description="Vulnerability settings for the model.",
    )

    hazard: Hazard = Field(
        default=...,
        description="Hazard settings for the model.",
    )

    # Properties
    @property
    def context(self) -> FileContext | None:
        """Return the context."""
        return self._context

    # Serializer(s)
    @field_serializer("output_dir")
    def serialize_path(self, value: Path, info: ValidationInfo) -> str:
        """Translate output directory to string."""
        context: FileContext = info.context or DEFAULT_CONTEXT
        return _relpath(value=value, root=context.config_dir)

    # Validators(s)
    @field_validator("loglevel", mode="after")
    @classmethod
    def validate_loglevel(cls, value: str):
        """Validate the loglevel validity."""
        if value not in LogLevels._member_map_:
            raise ValueError(f"Level ({value}) is not a valid log level.")
        return value

    @field_validator("output_dir", mode="after")
    @classmethod
    def validate_output_path(cls, value: Path, info: ValidationInfo):
        """Adjust the output directory to a full path."""
        context: FileContext = info.context or DEFAULT_CONTEXT
        context.output_dir = value
        if value.is_absolute():
            return value
        value = Path(context.config_dir, value)
        context.output_dir = value
        return value

    @field_validator("threads", mode="after")
    @classmethod
    def validate_threads(cls, value: int):
        max_threads = cpu_count()
        if value > max_threads:
            logger.warning(
                f"Given number of threads ('{value}') \
exceeds machine thread count ('{max_threads}')"
            )
            value = min(max_threads, value)
        return value

    @model_validator(mode="after")
    def set_settings_context(self, info: ValidationInfo):
        self._context = info.context or DEFAULT_CONTEXT
        return self

    # Class methods
    @classmethod
    def from_toml(cls, filename: Path | str) -> "BaseSettings":
        """Initialize the settings from a settings toml file.

        Parameters
        ----------
        filename : Path | str
            The path of the settings toml file.

        Returns
        -------
        Settings
            Validated settings.
        """
        filename = generic_file_check(file=filename)

        # Read the settings from the toml as a dict
        with open(file=filename, mode="rb") as reader:
            settings_dict = tomllib.load(reader)

        # Load the model settings and validate them
        obj = cls.model_validate(
            settings_dict,
            context=FileContext(config_dir=filename.parent),
        )
        # Return the settings
        return obj

    # User methods
    def to_dict(
        self,
        context: FileContext = DEFAULT_CONTEXT,
    ) -> dict[str, Any]:
        """Export to settings to a dictionary.

        Parameters
        ----------
        context : FileContext, optional
            The file context for input and output files, by default DEFAULT_CONTEXT.

        Returns
        -------
        dict[str, Any]
            The settings as a dictionary.
        """
        data = self.model_dump(
            context=self.context or context,
            exclude_none=True,
        )
        return data

    def update(self, **settings):
        """Update the settings with new ones."""
        updated = self.model_validate(
            {**self.to_dict(), **settings},
            context=self.context,
        )
        self.__dict__.update(updated)


# Helper function for the output files
def _derive_output_files(exposure, context, section):
    return [
        OutputFileModel.model_validate({FILE: item.file.name}, context=context)
        for item in exposure[section]
    ]


class GeomSettings(BaseSettings):
    """Geometry model settings."""

    type: Literal["geom"]

    geom: ModelGeom = Field(
        default=ModelGeom(),
        description="The model settings specific to the geometry model.",
    )

    output: list[OutputFileModel] | None = Field(
        default=None,
        description="The output file settings for the geometry model.",
    )

    exposure: list[ExposureGeometry] = Field(
        default=...,
        description="Exposure geometry settings for the FIAT model.",
    )

    # Validators
    @field_validator(EXPOSURE, mode="before")
    @classmethod
    def ensure_exposure_list(cls, value):
        """Ensure exposure list typing."""
        if not isinstance(value, list):
            value = [value]
        return value

    @field_validator(OUTPUT, mode="before")
    @classmethod
    def ensure_output_list(cls, value):
        """Ensure output list typing."""
        if not isinstance(value, list) and value is not None:
            value = [value]
        return value

    @model_validator(mode="after")
    def ensure_output_files(self, info: ValidationInfo):
        """Ensure the output files."""
        if self.output is None:
            self.output = _derive_output_files(
                self.exposure,
                info.context or DEFAULT_CONTEXT,
                slice(None, None),
            )
            return self
        self.output = self.output[: len(self.exposure)]
        if len(self.output) != len(self.exposure):
            self.output += _derive_output_files(
                exposure=self.exposure,
                context=info.context or DEFAULT_CONTEXT,
                section=slice(len(self.output), len(self.exposure)),
            )
        return self


class GridSettings(BaseSettings):
    """Geometry model settings."""

    type: Literal["grid"]

    grid: ModelGrid = Field(
        default=ModelGrid(),
        description="The model settings specific to the grid model.",
    )

    output: OutputFileModel | None = Field(
        default=None,
        description="The output file settings for the grid model.",
    )

    exposure: ExposureGrid = Field(
        default=...,
        description="Exposure grid settings for the FIAT model.",
    )

    # Validator(s)
    @model_validator(mode="after")
    def ensure_output_file(self, info: ValidationInfo):
        """Ensure an output file is set."""
        if self.output is not None:
            return self
        self.output = OutputFileModel.model_validate(
            {FILE: self.exposure.file.with_suffix(".tif").name},
            context=info.context or DEFAULT_CONTEXT,
        )
        return self


Settings = Annotated[
    GeomSettings | GridSettings,
    Field(discriminator="type"),
]


def load_settings(filename: Path | str) -> GeomSettings | GridSettings:
    """Read and load the settings toml into a validated structure.

    This is a standalone function similar to the `from_toml` methods of the
    BaseSettings class.
    """
    filename = generic_file_check(file=filename)

    # Read the file into a dictionary
    with open(filename, "rb") as reader:
        settings_dict = tomllib.load(reader)

    # Let the adapter sort out which settings class it should be
    settings: BaseSettings = TypeAdapter(Settings).validate_python(
        settings_dict,
        context=FileContext(config_dir=filename.parent),
    )

    # Return the settings
    return settings
