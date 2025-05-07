from multiprocessing import get_context
from typing import Generator

from fiat.job import execute_pool, generate_jobs


def test_generate_jobs_simple():
    # Setup some sinple
    jobs = generate_jobs(
        {"foo": [1, 2], "bar": [2], "baz": [3, 4]},
    )

    # Assert typing
    assert isinstance(jobs, Generator)
    # Make a list from the jobs to check
    jobs = list(jobs)
    assert len(jobs) == 4
    assert jobs[0] == {"foo": 1, "bar": 2, "baz": 3}
    assert jobs[3] == {"foo": 2, "bar": 2, "baz": 4}

    jobs = generate_jobs(
        {"foo": [1, 2, 3], "bar": [2, 3], "baz": [3, 4, 5]},
    )

    # Assert the size
    jobs = list(jobs)
    assert len(jobs) == 18


def test_generate_jobs_tied():
    # Tied two together
    jobs = generate_jobs(
        {"foo": [1, 2, 3], "bar": [2, 3], "baz": [3, 4, 5]},
        tied=["foo", "baz"],
    )

    # Assert the size
    jobs = list(jobs)
    assert len(jobs) == 6
    assert jobs[0] == {"foo": 1, "bar": 2, "baz": 3}
    assert jobs[1] == {"foo": 2, "bar": 2, "baz": 4}


# Dummy function to test
def multiply(x, y):
    return x * y


# Testing of the execution
def test_execute_pool_single_thread():
    # Setup the context
    ctx = get_context("spawn")

    # Execute the pool
    res = execute_pool(
        ctx=ctx,
        func=multiply,
        jobs=generate_jobs({"x": [2], "y": [4]}),
        threads=1,
    )

    # Assert the output
    assert res == [8]

    # Execute the pool with more than one job
    res = execute_pool(
        ctx=ctx,
        func=multiply,
        jobs=generate_jobs({"x": [2, 4], "y": [4, 5]}),
        threads=1,
    )

    assert res == [8, 10, 16, 20]


def test_execute_pool_multi_thread():
    # Setup the context
    ctx = get_context("spawn")

    # Execute the pool with more than one job
    res = execute_pool(
        ctx=ctx,
        func=multiply,
        jobs=generate_jobs({"x": [2, 4], "y": [4, 5]}),
        threads=2,
    )

    assert res == [8, 10, 16, 20]
