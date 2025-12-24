"""Worker functions for grid model."""

import importlib
from itertools import product
from pathlib import Path
from typing import Callable

import numpy as np

from fiat.fio import (
    GridIO,
    open_grid,
)
from fiat.model.util import vectorize_function
from fiat.struct import GridBand, Table
from fiat.struct.container import ExposureGridMeta, HazardMeta, VulnerabilityMeta
from fiat.util import create_2d_windows


def process_hazard(
    band: GridBand,
    window: tuple,
    vulnerability_meta: VulnerabilityMeta,
):
    """Small processor of hazard data chunk."""
    h = band[*window]
    h[h == band.nodata] = np.nan
    h = np.fmax(np.fmin(h, vulnerability_meta.max), vulnerability_meta.min)
    return h


def array_worker(
    hazard: GridIO,
    hazard_meta: HazardMeta,
    vulnerability: Table,
    vulnerability_meta: VulnerabilityMeta,
    exposure: GridIO,
    exposure_meta: ExposureGridMeta,
    fn_impact: Callable,
    window: tuple,
) -> np.ndarray:
    """_summary_.

    Parameters
    ----------
    hazard : GridIO
        _description_
    hazard_meta : HazardMeta
        _description_
    vulnerability : Table
        _description_
    vulnerability_meta : VulnerabilityMeta
        _description_
    exposure : GridIO
        _description_
    exposure_meta : ExposureGridMeta
        _description_
    fn_impact : Callable
        _description_
    window : tuple
        _description_

    Returns
    -------
    np.ndarray
        _description_
    """
    out_array = np.zeros((exposure_meta.nb + hazard_meta.risk, *window[2:])) * np.nan

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
            vulnerability=vulnerability,
            fn=exposure_meta.fn_list[0],
            sigdec=vulnerability_meta.sigdec,
        )
        bn += 1

    # Set the total damages
    for part, total in zip(exposure_meta.indices_new, exposure_meta.indices_total):
        mask = np.isnan([out_array[idx] for idx in part]).all(axis=0)
        out_array[total] = np.nansum([out_array[idx] for idx in part], axis=0)
        out_array[total][mask] = np.nan

    # Return the array
    return out_array


def worker(
    output_dir: Path,
    hazard: GridIO,
    hazard_meta: HazardMeta,
    vulnerability: Table,
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
    output_dir : Path
        The directory to which to write the output to.
    hazard : GridIO
        The hazard data.
    hazard_meta : HazardMeta
        Metadata specific to the hazard data.
    vulnerability : Table
        The vulnerability data.
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
    fn = getattr(module, "fn_impact_single")

    # Create the outgoing netcdf containing every exposure damages
    out_src = open_grid(
        Path(output_dir, f"{exposure.path.name}"),
        mode="w",
    )
    out_src.create(
        shape=exposure.shape_xy,
        nb=exposure_meta.nb,
        dtype=exposure.dtype,
        options=["FORMAT=NC4", "COMPRESS=DEFLATE"],
    )
    out_src.set_source_srs(exposure.srs)
    out_src.geotransform = exposure.geotransform

    # Set up the vectorized function
    fn_impact = vectorize_function(fn=fn, skip=hazard_meta.type_length + 1)

    # Loop through the windows
    for window in create_2d_windows(shape=chunk[2:], origin=chunk[0:2], chunk=(10, 10)):
        out_array = array_worker(
            hazard=hazard,
            hazard_meta=hazard_meta,
            vulnerability=vulnerability,
            vulnerability_meta=vulnerability_meta,
            exposure=exposure,
            exposure_meta=exposure_meta,
            fn_impact=fn_impact,
            window=window,
        )

        # Write the chunk
        for idx in range(exposure_meta.nb):
            out_src[idx].write_chunk(out_array[idx], window[0:2])

    # Close and dereference
    out_src.close()
    out_src = None
