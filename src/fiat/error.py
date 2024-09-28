"""Custom errors for FIAT."""


class DriverNotFoundError(Exception):
    """_summary_."""

    def __init__(self, gog, path):
        self.base = f"{gog} data"
        self.msg = f"Extension of file: {path.name} not recoqnized"
        super(DriverNotFoundError, self).__init__(f"{self.base} -> {self.msg}")

    def __str__(self):
        return f"{self.base} -> {self.msg}"


class GenericFIATError(Exception):
    """_summary_."""

    pass


class FIATDataError(Exception):
    """_summary_."""

    def __init__(self, msg):
        self.base = "Data error"
        self.msg = msg

    def __str__(self):
        return f"{self.base} -> {self.msg}"
