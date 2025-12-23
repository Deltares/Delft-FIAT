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
from fiat.struct import Table
from fiat.struct.container import ExposureGridMeta, HazardMeta, VulnerabilityMeta
from fiat.util import create_2d_windows


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
    for exp, haz in product(exposure.bands, hazard.bands):
        # Get the data and set nodata to nan
        # Get the hazard data clipped to the vulnerability index
        h = haz[*window]
        h[h == haz.nodata] = np.nan
        h = np.fmax(np.fmin(h, vulnerability_meta.max), vulnerability_meta.min)
        # Get the hazard data
        e = exp[*window]
        e[e == exp.nodata] = np.nan

        # Call the impact function
        out_array = fn_impact(
            h,
            e,
            fact=1,
            vulnerability=vulnerability,
            fn=exposure_meta.fn_list[0],
            sigdec=vulnerability_meta.sigdec,
        )
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
    # Set some variables for the calculations
    band_n = ""

    # Setup the hazard type module
    module = importlib.import_module(f"fiat.method.{hazard_meta.type}")
    fn = getattr(module, "fn_impact_single")

    # Create the outgoing netcdf containing every exposure damages
    out_src = open_grid(
        Path(output_dir, f"output{band_n}.nc"),
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
    na = fn.__code__.co_argcount
    excluced = set(fn.__code__.co_varnames[2:na])
    fn_impact = np.vectorize(fn, otypes=[np.float32], excluded=excluced)

    # Loop through the windows
    for window in create_2d_windows(shape=chunk[2:], origin=chunk[0:2], chunk=(10, 10)):
        out_array = array_worker(
            hazard=hazard,
            hazard_meta=hazard_meta,
            vulnerability=vulnerability,
            vulnerability_meta=vulnerability_meta,
            exposure=exposure,
            exposure_meta=[],
            fn_impact=fn_impact,
            window=window,
        )

        # Write the chunk
        for idx in range(exposure_meta.nb):
            out_src[idx].write_chunk(out_array, window[0:2])

    # Close and dereference
    out_src.close()
    out_src = None
