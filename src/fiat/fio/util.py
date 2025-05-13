"""Utility of the I/O module."""

from fiat.fio.grid import GridIO


def deter_band_names(
    obj: GridIO,
) -> list:
    """Determine the names of the bands.

    If the bands do not have any names of themselves,
    they will be set to a default.
    """
    _names = []
    for n in range(obj.size):
        name = obj.get_band_name(n + 1)
        if not name:
            _names.append(f"band{n+1}")
            continue
        _names.append(name)

    return _names
