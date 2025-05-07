"""Creating run jobs in fiat."""

from concurrent.futures import ProcessPoolExecutor, wait
from itertools import product
from multiprocessing.context import SpawnContext
from typing import Callable, Generator

from fiat.log import spawn_logger

logger = spawn_logger("fiat.job")


def generate_jobs(
    d: dict,
    tied: tuple | list = None,
) -> dict:  # type: ignore
    """Generate jobs.

    Parameters
    ----------
    d : dict
        Dictionary of elements, either containing single values or iterables.
    tied : tuple | list, optional
        Values in the dictionary that depend on each other.

    Returns
    -------
    dict
        Dictionary containing the job.
    """
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
    ctx: SpawnContext,
    func: Callable,
    jobs: Generator,
    threads: int,
):
    """Execute a python process pool.

    Parameters
    ----------
    ctx : SpawnContext
        Context of the current process.
    func : Callable
        To be executed function.
    jobs : Generator
        A job generator. Returns single dictionaries.
    threads : int
        Number of threads.
    """
    # If there is only one thread needed, execute in the main process
    res = []
    if threads == 1:
        for job in jobs:
            r = func(**job)
            res.append(r)
        return res

    # If there are more threads needed however
    processes = []
    # Setup the multiprocessing pool
    pool = ProcessPoolExecutor(
        max_workers=threads,
        mp_context=ctx,
    )

    # Go through all the jobs
    for job in jobs:
        pr = pool.submit(
            func,
            **job,
        )
        processes.append(pr)

    # wait for all jobs to conclude
    wait(processes)

    # Ask for the result to see if everything went well
    for pr in processes:
        r = pr.result()
        res.append(r)

    pool.shutdown(wait=False)

    return res
