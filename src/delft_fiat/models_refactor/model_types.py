from typing import List, Tuple, TypeAlias, Union

from delft_fiat.io import CSVLarge, CSVSmall, GeomSource, GridSource

ExposureMap: TypeAlias = Union[GeomSource, GridSource]

CSV: TypeAlias = Union[CSVLarge, CSVSmall]

DamageType: TypeAlias = Tuple[str, str]
