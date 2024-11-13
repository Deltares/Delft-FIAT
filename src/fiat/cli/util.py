"""Util for cli."""

import cProfile
import pstats
import sys
from pathlib import Path
from typing import Callable

from fiat.cfg import ConfigReader
from fiat.log import Logger


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
    logger: Logger,
    *args,
):
    """Cli friendly run for/ with logging exceptions."""
    try:
        out = func(*args)
    except BaseException:
        t, v, tb = sys.exc_info()
        msg = ",".join([str(item) for item in v.args])
        if t is KeyboardInterrupt:
            msg = "KeyboardInterrupt"
        logger.error(msg)
        # Exit with code 1
        sys.exit(1)
    else:
        return out


def run_profiler(
    func: Callable,
    profile: str,
    cfg: ConfigReader,
    logger: Logger,
):
    """Run the profiler from cli."""
    logger.warning("Running profiler...")

    # Setup the profiler and run the function
    profiler = cProfile.Profile()
    profiler.enable()
    run_log(func, logger=logger)
    profiler.disable()

    # Save all the stats
    profile_out = cfg.get("output.path") / profile
    profiler.dump_stats(profile_out)
    logger.info(f"Saved profiling stats to: {profile_out}")

    # Save a human readable portion to a text file
    txt_out = cfg.get("output.path") / "profile.txt"
    with open(txt_out, "w") as _w:
        _w.write(f"Delft-FIAT profile ({cfg.filepath}):\n\n")
        stats = pstats.Stats(profiler, stream=_w)
        _ = stats.sort_stats("tottime").print_stats()
        logger.info(f"Saved profiling stats in human readable format: {txt_out}")
