"""Worker functions for grid model."""

import importlib
from itertools import chain, product
from typing import Callable

import numpy as np

from fiat.driver import NetcdfReader, NetcdfVariable
from fiat.driver.geotiff.writer import TileSink
from fiat.model.meta import (
    ExposureGridMeta,
    HazardMeta,
    RunMeta,
    VulnerabilityMeta,
)
from fiat.typing import MethodType
from fiat.util import FIAT_METHOD, FN, NODATA_VALUE


def initialize_pool(desc: dict, lock):
    """Initialise a worker with a :class:`TileSink` bound to the shared output."""
    global tilesink
    tilesink = TileSink(desc, lock)


def process_hazard(
    band: NetcdfVariable,
    vulnerability_meta: VulnerabilityMeta,
):
    """Small processor of hazard data chunk."""
    band.data[band.data == band.nodata] = np.nan
    band.data = np.fmax(
        np.fmin(band.data, vulnerability_meta.max),
        vulnerability_meta.min,
    )


def array_worker(
    out_array: np.ndarray[np.float32],
    run_meta: RunMeta,
    hazard: NetcdfReader,
    hazard_meta: HazardMeta,
    vulnerability_meta: VulnerabilityMeta,
    exposure: NetcdfReader,
    exposure_meta: ExposureGridMeta,
    fn_impact: Callable,
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

    Returns
    -------
    np.ndarray
        The calculated impact.
    """
    bn = 0
    # Process the hazard data
    for idx in chain.from_iterable(hazard_meta.indices_run):
        process_hazard(hazard[idx], vulnerability_meta=vulnerability_meta)

    # Loop through the default calculation combinations
    for haz_indices, exp_index in product(
        hazard_meta.indices_run,
        exposure_meta.indices_default,
    ):
        # Get the exposure data
        exp = exposure[exp_index]
        exp.data[exp.data == exp.nodata] = np.nan

        # Call the impact function
        out_array[exposure_meta.indices_default_new[bn]] = fn_impact(
            *[hazard[idx].data for idx in haz_indices],
            exp.data,
            fact=1,
            fn_curve=vulnerability_meta.fn[exp.get_attr(FN)],
        )
        bn += 1

    # Loop through the categorized indices
    for haz_indices, (exp_index, exp_cat_indices) in product(
        hazard_meta.indices_run,
        zip(exposure_meta.indices_cat, exposure_meta.indices_cat_values),
    ):
        # Get the exposure data
        exp = exposure[exp_index]
        # Loop through the integer header based vulnerability curves
        for key, fn in vulnerability_meta.fn.items():
            try:
                key = int(key)
            except BaseException:
                continue
            if key == 0:
                continue
            mask = exp.data == key
            if mask.sum() == 0:
                continue
            bn = 0
            # Only when there is an active mask, go through all categories value
            # categories... funny aint it
            for cat_value_idx in exp_cat_indices:
                values = (
                    fn_impact(
                        *[[hazard[idx].data[mask] for idx in haz_indices]],
                        exposure[cat_value_idx][key],
                        fn,
                        1,
                    )
                    * run_meta.cell_size
                )
                values[values == 0] = np.nan
                out_array[exposure_meta.indices_cat_new[bn], mask] = values
                bn += 1

    # Set the total damages
    for part, total in zip(exposure_meta.indices_new, exposure_meta.indices_total):
        mask = np.isnan([out_array[idx] for idx in part]).all(axis=0)
        out_array[total] = np.nansum(
            [out_array[idx] for idx in part],
            axis=0,
        )
        out_array[total][mask] = np.nan

    # Risk
    if run_meta.risk:
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
    run_meta: RunMeta,
    hazard: NetcdfReader,
    hazard_meta: HazardMeta,
    vulnerability_meta: VulnerabilityMeta,
    exposure: NetcdfReader,
    exposure_meta: ExposureGridMeta,
    window: tuple,
):
    """Compute one output tile and write it directly to the shared GeoTIFF.

    Each job owns exactly one tile-aligned ``window``; the worker computes all
    output bands for that tile and appends the compressed tile to the shared
    output file through its :class:`TileSink` (set up by
    :func:`initialize_pool`). Returns the written tile's index records so
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
    """
    # Setup the hazard type module
    method: MethodType = importlib.import_module(f"{FIAT_METHOD}.{run_meta.type}")
    fn_impact = method.fn_impact

    row_slice, col_slice = window
    h = row_slice.stop - row_slice.start
    w = col_slice.stop - col_slice.start

    # Read the window in memory
    hazard.load(*window)
    exposure.load(*window)

    # A fresh (padded) output block for this tile.
    out_array = np.full((exposure_meta.nb, h, w), np.nan, dtype=np.float32)
    array_worker(
        out_array=out_array,
        run_meta=run_meta,
        hazard=hazard,
        hazard_meta=hazard_meta,
        vulnerability_meta=vulnerability_meta,
        exposure=exposure,
        exposure_meta=exposure_meta,
        fn_impact=fn_impact,
    )

    # Fill nodata and write the tile directly to the shared output file.
    tile = out_array.copy()
    tile[np.isnan(tile)] = NODATA_VALUE
    return tilesink.write_block((col_slice.start, row_slice.start), tile)
