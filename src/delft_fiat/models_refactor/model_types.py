from typing import TypeAlias, Union

from delft_fiat.io import CSVLarge, CSVSmall, GeomSource, GridSource

ExposureMap: TypeAlias = Union[GeomSource, GridSource]

CSV: TypeAlias = Union[CSVLarge, CSVSmall]
