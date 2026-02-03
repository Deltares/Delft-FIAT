"""Worker functions for grid model."""

import importlib
from itertools import product
from multiprocessing.queues import Queue
from typing import Callable

import numpy as np

from fiat.fio import (
    GridIO,
)
from fiat.struct import GridBand
from fiat.struct.container import ExposureGridMeta, HazardMeta, VulnerabilityMeta
from fiat.util import create_2d_windows


def initialize_pool(q: Queue):
    """Small initializer for the multiprocessing pool."""
    global pipeline
    pipeline = q


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
    out_array = (
        np.zeros(
            (exposure_meta.nb + hazard_meta.risk, *window[2:]),
            dtype=np.float32,
        )
        * np.nan
    )

    bn = 0
    # Loop through the combinations
    for exp, haz_indices in product(exposure.bands, hazard_meta.indices_run):
        # Get and process the hazard data
        h = [
            process_hazard(
                hazard[idx], window=window, vulnerability_meta=vulnerability_meta
            )
            for idx in haz_indices
        ]
        # Get the exposure data
        e = exp[*window]
        e[e == exp.nodata] = np.nan

        # Call the impact function
        out_array[bn] = fn_impact(
            *h,
            e,
            fact=1,
            fn_curve=vulnerability_meta.fn[exp.get_meta("fn")],
        )
        bn += 1

    # Set the total damages
    for part, total in zip(exposure_meta.indices_new, exposure_meta.indices_total):
        mask = np.isnan([out_array[idx] for idx in part]).all(axis=0)
        out_array[total] = np.nansum([out_array[idx] for idx in part], axis=0)
        out_array[total][mask] = np.nan

    # Risk
    if hazard_meta.risk:
        mask = np.isnan(out_array[exposure_meta.indices_total]).all(axis=0)
        out_array[-1] = np.nansum(
            [
                f * a
                for f, a in zip(
                    hazard_meta.density, out_array[exposure_meta.indices_total]
                )
            ],
            axis=0,
        )
        out_array[-1][mask] = np.nan

    # Return the array
    return out_array


def worker(
    shm_name: str,
    hazard: GridIO,
    hazard_meta: HazardMeta,
    vulnerability_meta: VulnerabilityMeta,
    exposure: GridIO,
    exposure_meta: ExposureGridMeta,
    chunk: tuple,
):
    """Run the grid model.

    This is the worker function corresponding to the run method \
of the [GridIO](/api/GeomIO.qmd) object.

    Parameters
    ----------
    shm_name : Path
        The name of the shared memory.
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
    module = importlib.import_module(f"fiat.method.{hazard_meta.type}")
    fn_impact = getattr(module, "fn_impact_single")

    # Loop through the windows
    for window in create_2d_windows(
        shape=chunk[2:],
        origin=chunk[0:2],
        window=(2, 2),
    ):
        _ = array_worker(
            hazard=hazard,
            hazard_meta=hazard_meta,
            vulnerability_meta=vulnerability_meta,
            exposure=exposure,
            exposure_meta=exposure_meta,
            fn_impact=fn_impact,
            window=window,
        )

        # Write the chunk
        for idx in range(exposure_meta.nb):
            # out_src[idx].write(out_array[idx], window[0:2])
            pass

    # Close and dereference
