"""Generic container."""

import copy
from dataclasses import dataclass
from typing import Any

__all__ = ["Container", "ExposureMeta", "VulnerabilityMeta"]


class Container:
    """Dataset container.

    Datasets are accessable via <Container>.ds[n].
    """

    _base = "ds"

    def __new__(cls):
        """Creation."""
        obj = object.__new__(cls)
        obj._i = 0
        obj._db = []
        obj._h = []
        return obj

    def __len__(self) -> int:
        return len(self._h)

    def __iter__(self):
        self._l = 0
        return self

    def __next__(self) -> Any:
        if self._l < len(self._db):
            self._l += 1
            return self.__dict__[self._db[self._l - 1]]
        else:
            raise StopIteration

    def __setitem__(self, key: str, value: Any):
        if not isinstance(key, str):
            raise TypeError("'key' should be of type 'str'")
        h = hash(value)
        if h in self._h:
            return
        self._h.append(h)
        self._db.append(key)
        self.__dict__[key] = value

    def clear(self) -> None:
        """Clear the entire container."""
        cur = copy.deepcopy(self._h)
        for item in cur:
            self.delete(item)

    def delete(self, key: str | int) -> None:
        """Remove a dataset from the container."""
        if isinstance(key, str):
            idx = self._db.index(key)
        elif isinstance(key, int):
            idx = self._h.index(key)
        else:
            raise TypeError("'key' should either be of type 'int' or 'str'")
        _ = self._h.pop(idx)
        _ = self.__dict__.pop(self._db[idx])
        _ = self._db.pop(idx)

    def set(self, value: Any) -> None:
        """Set a dataset."""
        self._i += 1
        n = f"{self._base}{self._i}"
        self[n] = value


@dataclass
class ExposureMeta:
    """Small container for exposure metadata."""

    indices_new: list
    indices_spec: list
    indices_total: list
    indices_type: dict
    new: list
    type_length: int


@dataclass
class HazardMeta:
    """Small container for exposure metadata."""

    density: list
    names: list
    rp: list
    risk: bool
    type: str = "flood"


@dataclass
class VulnerabilityMeta:
    """Small container for some vulnerability metadata."""

    min: float | int
    max: float | int
    sigdec: int
