"""Worker functions for grid model."""

import importlib
from typing import Any, Callable

import numpy as np

from fiat.driver import NetcdfReader
from fiat.driver.geotiff.writer import TileSink
from fiat.model.meta import (
    ExposureGridMeta,
    HazardMeta,
    RunMeta,
)
from fiat.util import FIAT_METHOD, NODATA_VALUE


def initialize_pool(desc: dict, lock):
    """Initialise a worker with a :class:`TileSink` bound to the shared output."""
    global tilesink
    tilesink = TileSink(desc, lock)


def array_worker(
    out_array: np.ndarray[np.float32],
    run_meta: RunMeta,
    hazard: NetcdfReader,
    hazard_meta: HazardMeta,
    exposure: NetcdfReader,
    exposure_meta: ExposureGridMeta,
    fns: dict[str, Callable[..., Any]],
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
    exposure : NetcdfReader
        The exposure data.
    exposure_meta : ExposureGridMeta
        Metadata specific to the exposure data (the calculation units).
    fns : dict[str, Callable]
        The impact functions per method name.

    Returns
    -------
    np.ndarray
        The calculated impact.
    """
    # Process the hazard data, every used band once
    bands = {
        idx
        for unit in exposure_meta.units
        for indices in unit.hazard_indices
        for idx in indices
    }
    for idx in sorted(bands):
        band = hazard[idx]
        # Integer bands are cast to float so nodata can become nan
        if not np.issubdtype(band.data.dtype, np.floating):
            band.data = band.data.astype(np.float64)
        if band.nodata is not None:
            band.data[band.data == band.nodata] = np.nan

    # Loop through the calculation units
    for unit in exposure_meta.units:
        fn_impact = fns[unit.method]
        exp = exposure[unit.exp_index]
        if unit.value_index is None:
            if exp.nodata is not None:
                exp.data[exp.data == exp.nodata] = np.nan
            for haz_indices, out_index in zip(unit.hazard_indices, unit.out_indices):
                out_array[out_index] = fn_impact(
                    tuple(hazard[idx].data for idx in haz_indices),
                    exp.data,
                    unit.curves,
                    1,
                )
            continue

        # Categorized, the exposure value per category from the value variable
        assert isinstance(unit.curves, dict)
        value_var = exposure[unit.value_index]
        coords = exposure.dims[value_var.dims[0]][:].tolist()
        for key, curves in unit.curves.items():
            if key not in coords:
                continue
            mask = exp.data == key
            if mask.sum() == 0:
                continue
            value = value_var[coords.index(key)]
            for haz_indices, out_index in zip(unit.hazard_indices, unit.out_indices):
                values = (
                    fn_impact(
                        tuple(hazard[idx].data[mask] for idx in haz_indices),
                        value,
                        curves,
                        1,
                    )
                    * run_meta.cell_size
                )
                values[values == 0] = np.nan
                out_array[out_index, mask] = values

    # Set the total damages
    for part, total in zip(exposure_meta.totals, exposure_meta.indices_total):
        mask = np.isnan([out_array[idx] for idx in part]).all(axis=0)
        out_array[total] = np.nansum(
            [out_array[idx] for idx in part],
            axis=0,
        )
        out_array[total][mask] = np.nan

    # Risk
    if run_meta.risk:
        mask = np.isnan(out_array[exposure_meta.indices_total]).all(axis=0)
        out_array[exposure_meta.index_ead] = np.nansum(
            [
                f * a
                for f, a in zip(
                    hazard_meta.density, out_array[exposure_meta.indices_total]
                )
            ],
            axis=0,
        )
        out_array[exposure_meta.index_ead][mask] = np.nan

    # Return the array
    return out_array


def worker(
    run_meta: RunMeta,
    hazard: NetcdfReader,
    hazard_meta: HazardMeta,
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
    exposure : NetcdfReader
        The exposure data.
    exposure_meta : ExposureGridMeta
        Metadata specific to the exposure data.
    window : tuple[slice, slice]
        The tile-aligned ``(row_slice, col_slice)`` for this job.
    """
    # Import the methods of the calculation units once
    fns = {
        name: importlib.import_module(f"{FIAT_METHOD}.{name}").fn_impact
        for name in {unit.method for unit in exposure_meta.units}
    }

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
        exposure=exposure,
        exposure_meta=exposure_meta,
        fns=fns,
    )

    # Fill nodata and write the tile directly to the shared output file.
    tile = out_array.copy()
    tile[np.isnan(tile)] = NODATA_VALUE
    return tilesink.write_block((col_slice.start, row_slice.start), tile)
