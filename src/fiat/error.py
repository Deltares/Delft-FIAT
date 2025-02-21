"""Custom errors for FIAT."""


class DriverNotFoundError(Exception):
    """Custom driver not found class."""

    def __init__(self, gog, path):
        self.base = f"{gog} data"
        self.msg = f"Extension of file: {path.name} not recoqnized"
        super(DriverNotFoundError, self).__init__(f"{self.base} -> {self.msg}")

    def __str__(self):
        return f"{self.base} -> {self.msg}"


class FIATDataError(Exception):
    """Custom FIAT error class."""

    def __init__(self, msg):
        self.base = "Data error"
        self.msg = msg

    def __str__(self):
        return f"{self.base} -> {self.msg}"
