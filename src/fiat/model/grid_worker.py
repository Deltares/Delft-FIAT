"""Worker functions for grid model."""

import importlib
from itertools import product
from multiprocessing.connection import Connection
from multiprocessing.queues import Queue
from multiprocessing.shared_memory import SharedMemory
from typing import Callable

import numpy as np

from fiat.fio import (
    GridIO,
)
from fiat.model.grid_writer import GridItem
from fiat.model.util import create_2d_windows
from fiat.struct import GridBand
from fiat.struct.container import ExposureGridMeta, HazardMeta, VulnerabilityMeta
from fiat.thread import Sender
from fiat.typing import MethodsProtocol


def initialize_pool(q: Queue, p: dict[str, Connection]):
    """Small initializer for the multiprocessing pool."""
    global signalqueue
    signalqueue = q
    global pipelines
    pipelines = p


def process_hazard(
    band: GridBand,
    window: tuple,
    vulnerability_meta: VulnerabilityMeta,
):
    """Small processor of hazard data chunk."""
    out_array = band[*window]
    out_array[out_array == band.nodata] = np.nan
    out_array = np.fmax(
        np.fmin(out_array, vulnerability_meta.max),
        vulnerability_meta.min,
    )
    return out_array


def array_worker(
    out_array: np.ndarray[np.float32],
    hazard: GridIO,
    hazard_meta: HazardMeta,
    vulnerability_meta: VulnerabilityMeta,
    exposure: GridIO,
    exposure_meta: ExposureGridMeta,
    fn_impact: Callable,
    window: tuple,
) -> np.ndarray:
    """Calculate the impact for a chunk of the exposure.

    Parameters
    ----------
    hazard : GridIO
        The hazard data.
    hazard_meta : HazardMeta
        Metadata specific to the hazard data.
    vulnerability_meta : VulnerabilityMeta
        Metadata specific to the vulnerability data.
    exposure : GridIO
        The exposure data.
    exposure_meta : ExposureGridMeta
        Metadata specific to the exposure data.
    fn_impact : Callable
        The impact function.
    window : tuple
        The window of the chunk.

    Returns
    -------
    np.ndarray
        The calculated impact.
    """
    bn = 0
    w, h = window[2:]
    # Loop through the combinations
    for exp, haz_indices in product(exposure.bands, hazard_meta.indices_run):
        # Get and process the hazard data
        hazard_data = [
            process_hazard(
                hazard[idx], window=window, vulnerability_meta=vulnerability_meta
            )
            for idx in haz_indices
        ]
        # Get the exposure data
        exposure_data = exp[*window]
        exposure_data[exposure_data == exp.nodata] = np.nan

        # Call the impact function
        out_array[bn, :h, :w] = fn_impact(
            *hazard_data,
            exposure_data,
            fact=1,
            fn_curve=vulnerability_meta.fn[exp.get_meta("fn")],
        )
        bn += 1

    # Set the total damages
    for part, total in zip(exposure_meta.indices_new, exposure_meta.indices_total):
        mask = np.isnan([out_array[idx, :h, :w] for idx in part]).all(axis=0)
        out_array[total, :h, :w] = np.nansum(
            [out_array[idx, :h, :w] for idx in part],
            axis=0,
        )
        out_array[total, :h, :w][mask] = np.nan

    # Risk
    if hazard_meta.risk:
        mask = np.isnan(out_array[exposure_meta.indices_total, :h, :w]).all(axis=0)
        out_array[-1, :h, :w] = np.nansum(
            [
                f * a
                for f, a in zip(
                    hazard_meta.density, out_array[exposure_meta.indices_total, :h, :w]
                )
            ],
            axis=0,
        )
        out_array[-1, :h, :w][mask] = np.nan

    # Return the array
    return out_array


def worker(
    mem_id: str,
    hazard: GridIO,
    hazard_meta: HazardMeta,
    vulnerability_meta: VulnerabilityMeta,
    exposure: GridIO,
    exposure_meta: ExposureGridMeta,
    chunk: tuple,
    window: tuple,
):
    """Run the grid model.

    This is the worker function corresponding to the run method \
of the [GridIO](/api/GeomIO.qmd) object.

    Parameters
    ----------
    mem_id : Path
        The identifier/ name of the shared memory.
    hazard : GridIO
        The hazard data.
    hazard_meta : HazardMeta
        Metadata specific to the hazard data.
    vulnerability_meta : VulnerabilityMeta
        Metadata specific to the vulnerability data.
    exposure : GridIO
        The exposure data.
    exposure_meta : ExposureGridMeta
        Metadata specific to the exposure data.
    chunk : tuple
        The specific chunk to process.
    """
    # Setup the hazard type module
    method: MethodsProtocol = importlib.import_module(f"fiat.method.{hazard_meta.type}")
    fn_impact = method.fn_impact

    # Setup the existing block of memory
    exshm = SharedMemory(name=mem_id)
    out_array = np.ndarray(
        shape=(exposure_meta.nb, *window),
        dtype=np.float32,
        buffer=exshm.buf,
    )
    sender = Sender(queue=signalqueue)

    # Loop through the windows
    for window_array in create_2d_windows(
        shape=chunk[2:],
        origin=chunk[0:2],
        window=window,
    ):
        # Do the calculations
        array_worker(
            out_array=out_array,
            hazard=hazard,
            hazard_meta=hazard_meta,
            vulnerability_meta=vulnerability_meta,
            exposure=exposure,
            exposure_meta=exposure_meta,
            fn_impact=fn_impact,
            window=window_array,
        )

        # Report back that it's done for this window
        record = GridItem(
            mem_id=mem_id,
            origin=window_array[:2],
            shape=window_array[2:],
        )
        sender.emit(record=record)

        # Wait for the parent to get back
        _ = pipelines[mem_id].recv()

    # Close the memory block
    out_array = None
    exshm.close()
