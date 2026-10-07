from pathlib import Path

from fiat.error import DriverNotFoundError, FIATDataError


def test_driver_not_found_error():
    # Set the error
    error = DriverNotFoundError("Grid", Path("/data/event_map.tif"))

    # Assert the composed message
    assert error.base == "Grid data"
    assert error.msg == "Extension of file: event_map.tif not recoqnized"
    assert str(error) == "Grid data -> Extension of file: event_map.tif not recoqnized"


def test_fiat_data_error():
    # Set the error
    error = FIATDataError("Missing exposure data")

    # Assert the composed message
    assert error.base == "Data error"
    assert error.msg == "Missing exposure data"
    assert str(error) == "Data error -> Missing exposure data"
