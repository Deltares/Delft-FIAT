"""The FIAT model workers."""

from itertools import product
from multiprocessing import Pool
from pathlib import Path
from typing import Callable, Generator

from fiat.util import NEWLINE_CHAR

GEOM_MIN_CHUNK = 50000
GEOM_MIN_WRITE_CHUNK = 20000


def csv_temp_file(
    p: Path | str,
    idx: int,
    index_col: str,
    columns: tuple | list,
):
    """_summary_.

    _extended_summary_
    """
    header = (
        f"{index_col},".encode() + ",".join(columns).encode() + NEWLINE_CHAR.encode()
    )
    with open(Path(p, f"{idx:03d}.dat"), "wb") as _tw:
        _tw.write(header)


def csv_def_file(
    p: Path | str,
    columns: tuple | list,
):
    """_summary_.

    _extended_summary_
    """
    header = b""
    header += ",".join(columns).encode()
    header += NEWLINE_CHAR.encode()

    with open(p, "wb") as _dw:
        _dw.write(header)


def geom_threads(
    cpu_count: int,
    haz_layers: int,
    chunks: int,
):
    """_summary_.

    _extended_summary_
    """
    n = 1
    if chunks == 0:
        chunks = 1
    n = chunks * haz_layers
    n = min(cpu_count, n)

    return n


def generate_jobs(
    d: dict,
    tied: tuple | list = None,
):
    """_summary_."""
    arg_list = []
    single_var = None
    if tied is not None:
        single_var = "_".join(tied)
        d[single_var] = list(zip(*[d[var] for var in tied]))
        for var in tied:
            del d[var]
    for arg in d.values():
        if not isinstance(arg, (tuple, list, range, zip)):
            arg = [
                arg,
            ]
        arg_list.append(arg)
    for element in product(*arg_list):
        kwargs = dict(zip(d.keys(), element))
        if single_var is not None:
            values = kwargs[single_var]
            for var, value in zip(tied, values):
                kwargs[var] = value
            del kwargs[single_var]
        yield kwargs


def execute_pool(
    func: Callable,
    jobs: Generator,
    threads: int,
):
    """_summary_."""
    # If there is only one thread needed, execute in the main process
    if threads == 1:
        for job in jobs:
            func(**job)
        return

    # If there are more threads needed however
    processes = []
    # Setup the multiprocessing pool
    pool = Pool(processes=threads)

    # Go through all the jobs
    for job in jobs:
        pr = pool.apply_async(
            func=func,
            kwds=job,
        )
        processes.append(pr)

    # wait for all jobs to conclude
    for pr in processes:
        pr.get()

    pool.close()
    pool.join()
