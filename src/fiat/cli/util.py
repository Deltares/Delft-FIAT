"""Util for cli."""

import sys
from pathlib import Path
from typing import Callable

from fiat.log import Log


def file_path_check(path):
    """Cli friendly version of path checking."""
    root = Path.cwd()
    path = Path(path)
    if not path.is_absolute():
        path = Path(root, path)
    if not (path.is_file() | path.is_dir()):
        raise FileNotFoundError(f"{str(path)} is not a valid path")
    return path


def run_log(
    func: Callable,
    logger: Log,
):
    """Cli friendly run for/ with logging exceptions."""
    try:
        func()
    except BaseException:
        t, v, tb = sys.exc_info()
        msg = ",".join([str(item) for item in v.args])
        if t is KeyboardInterrupt:
            msg = "KeyboardInterrupt"
        logger.error(msg)
        # Exit with code 1
        sys.exit(1)
