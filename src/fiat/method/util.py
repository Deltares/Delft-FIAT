"""Calculation utility."""

from fiat.util import mean

ZONAL_METHODS = {
    "max": max,
    "mean": mean,
    "min": min,
}

# Integer method codes for the compiled ``zonal_reduce`` (see fiat._core._zonal).
ZONAL_CODES = {
    "mean": 0,
    "max": 1,
    "min": 2,
}
