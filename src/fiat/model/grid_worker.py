"""Worker functions for grid model."""

import importlib
from itertools import product
from typing import Callable

import numpy as np

from fiat.container import (
    ExposureGridMeta,
    HazardMeta,
    RunMeta,
    VulnerabilityMeta,
)
from fiat.driver import NetcdfReader, NetcdfVariable
from fiat.driver.geotiff.writer import TileSink
from fiat.typing import MethodType
from fiat.util import FIAT_METHOD, FN, NODATA_VALUE


def initialize_geotiff_pool(desc: dict, lock):
    """Initialise a worker with a :class:`TileSink` bound to the shared output."""
    global tilesink
    tilesink = TileSink(desc, lock)


def process_hazard(
    band: NetcdfVariable,
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
    run_meta: RunMeta,
    hazard: NetcdfReader,
    hazard_meta: HazardMeta,
    vulnerability_meta: VulnerabilityMeta,
    exposure: NetcdfReader,
    exposure_meta: ExposureGridMeta,
    fn_impact: Callable,
    window: tuple,
) -> np.ndarray:
    """Calculate the impact for a chunk of the exposure.

    Parameters
    ----------
    out_array : np.ndarray
        The array to which to put the output data in.
    run_meta : RunMeta
        Configurations runtime metadata.
    hazard : NetcdfReader
        The hazard data.
    hazard_meta : HazardMeta
        Metadata specific to the hazard data.
    vulnerability_meta : VulnerabilityMeta
        Metadata specific to the vulnerability data.
    exposure : NetcdfReader
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
    h = window[0].stop - window[0].start
    w = window[1].stop - window[1].start
    # Loop through the combinations
    for exp, haz_indices in product(
        exposure.variables.values(),
        hazard_meta.indices_run,
    ):
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
            fn_curve=vulnerability_meta.fn[exp.get_attr(FN)],
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
    if run_meta.risk:
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
    run_meta: RunMeta,
    hazard: NetcdfReader,
    hazard_meta: HazardMeta,
    vulnerability_meta: VulnerabilityMeta,
    exposure: NetcdfReader,
    exposure_meta: ExposureGridMeta,
    window: tuple,
    chunk: tuple,
):
    """Compute one output tile and write it directly to the shared GeoTIFF.

    Each job owns exactly one tile-aligned ``window``; the worker computes all
    output bands for that tile and appends the compressed tile to the shared
    output file through its :class:`TileSink` (set up by
    :func:`initialize_geotiff_pool`). Returns the written tile's index records so
    the parent can rebuild the tile index.

    Parameters
    ----------
    run_meta : RunMeta
        The configurations runtime meta.
    hazard : NetcdfReader
        The hazard data.
    hazard_meta : HazardMeta
        Metadata specific to the hazard data.
    vulnerability_meta : VulnerabilityMeta
        Metadata specific to the vulnerability data.
    exposure : NetcdfReader
        The exposure data.
    exposure_meta : ExposureGridMeta
        Metadata specific to the exposure data.
    window : tuple[slice, slice]
        The tile-aligned ``(row_slice, col_slice)`` for this job.
    chunk : tuple
        The tile size as ``(height, width)``.
    """
    # Setup the hazard type module
    method: MethodType = importlib.import_module(f"{FIAT_METHOD}.{run_meta.type}")
    fn_impact = method.fn_impact

    row_slice, col_slice = window
    h = row_slice.stop - row_slice.start
    w = col_slice.stop - col_slice.start

    # A fresh (padded) output block for this tile.
    out_array = np.full((exposure_meta.nb, *chunk), np.nan, dtype=np.float32)
    array_worker(
        out_array=out_array,
        run_meta=run_meta,
        hazard=hazard,
        hazard_meta=hazard_meta,
        vulnerability_meta=vulnerability_meta,
        exposure=exposure,
        exposure_meta=exposure_meta,
        fn_impact=fn_impact,
        window=window,
    )

    # Fill nodata and write the tile directly to the shared output file.
    tile = out_array[:, :h, :w].copy()
    tile[np.isnan(tile)] = NODATA_VALUE
    return tilesink.write_block((col_slice.start, row_slice.start), tile)
