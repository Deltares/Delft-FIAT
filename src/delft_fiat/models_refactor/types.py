from typing import NewType, Tuple, TypeAlias, TypedDict, TypeVar, Union

from zipp import Path

from delft_fiat.io import CSVLarge, CSVSmall, GeomSource, GridSource

ExposureMap: TypeAlias = Union[GeomSource, GridSource]

CSV: TypeAlias = Union[CSVLarge, CSVSmall]

DamageType: TypeAlias = Tuple[str, str]

DamageFunc: TypeAlias = Tuple[str, str]

DamageCurve: TypeAlias = Tuple[Tuple[float], Tuple[float]]

vector = NewType("vector", str)
raster = NewType("raster", str)
coordinate = NewType("coordinate", str)

ModelType: TypeAlias = Union[vector, raster, coordinate]


class ExposureConfig(TypedDict):
    type: ModelType
    file: Path
    dbase_file: Path
    crs: str
