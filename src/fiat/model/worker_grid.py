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
from fiat.struct.container import HazardMeta, VulnerabilityMeta


def array_worker(
    hazard: GridIO,
    hazard_meta: HazardMeta,
    vulnerability: Table,
    vulnerability_meta: VulnerabilityMeta,
    exposure: GridIO,
    exposure_meta: type,
    fn_impact: Callable,
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
    exposure_meta : type
        _description_
    fn_impact : Callable
        _description_
    """
    for exp, haz in product(hazard.bands):
        pass
    pass


def worker(
    output_dir: Path,
    hazard: GridIO,
    hazard_meta: HazardMeta,
    vulnerability: Table,
    vulnerability_meta: VulnerabilityMeta,
    exposure: GridIO,
):
    """Run the geometry model.

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
    """
    # Set some variables for the calculations
    exp_bands = []
    write_bands = []
    exp_nds = []
    dmfs = []
    band_n = ""

    # Setup the hazard type module
    module = importlib.import_module(f"fiat.method.{hazard_meta.type}")
    fn_impact = getattr(module, "fn_impact")

    # Create the outgoing netcdf containing every exposure damages
    out_src = open_grid(
        Path(output_dir, f"output{band_n}.nc"),
        mode="w",
    )
    out_src.create(
        shape=exposure.shape_xy,
        nb=exposure.size + 1,
        dtype=exposure.dtype,
        options=["FORMAT=NC4", "COMPRESS=DEFLATE"],
    )
    out_src.set_source_srs(exposure.srs)
    out_src.geotransform = exposure.geotransform

    # Prepare some stuff for looping
    for idx in range(exposure.size):
        exp_bands.append(exposure[idx + 1])
        write_bands.append(out_src[idx + 1])
        exp_nds.append(exp_bands[idx].nodata)
        write_bands[idx].src.SetNoDataValue(exp_nds[idx])
        dmfs.append(exp_bands[idx].get_metadata_item("fn_damage"))

    for i in range(4):
        _ = array_worker(
            hazard=hazard,
            hazard_meta=hazard_meta,
            vulnerability=vulnerability,
            vulnerability_meta=vulnerability_meta,
            exposure=exposure,
            exposure_meta=[],
            fn_impact=fn_impact,
        )

    # Going trough the chunks
    for _w, h_ch in hazard[0]:
        # Per exposure band
        for idx, exp_band in enumerate(exp_bands):
            e_ch = exp_band[_w]

            # See if there is any exposure data
            out_ch = np.full(e_ch.shape, exp_nds[idx])
            e_ch = np.ravel(e_ch)
            _coords = np.where(e_ch != exp_nds[idx])[0]
            if len(_coords) == 0:
                write_bands[idx].src.WriteArray(out_ch, *_w[:2])
                continue

            # See if there is overlap with the hazard data
            e_ch = e_ch[_coords]
            h_1d = np.ravel(h_ch)
            h_1d = h_1d[_coords]
            _hcoords = np.where(h_1d != hazard[0].nodata)[0]

            if len(_hcoords) == 0:
                write_bands[idx].src.WriteArray(out_ch, *_w[:2])
                continue

            # Do the calculations
            _coords = _coords[_hcoords]
            e_ch = e_ch[_hcoords]
            h_1d = h_1d[_hcoords]
            h_1d = h_1d.clip(vulnerability_meta.min, vulnerability_meta.max)

            dmm = [vulnerability[round(float(n), 2), dmfs[idx]] for n in h_1d]
            e_ch = e_ch * dmm

            idx2d = np.unravel_index(_coords, *[exposure._chunk])
            out_ch[idx2d] = e_ch

            # Write it to the band in the outgoing file
            write_bands[idx].write_chunk(out_ch, _w[:2])

    # Flush the cache and dereference
    for _w in write_bands[:]:
        write_bands.remove(_w)
        _w.close()
        _w = None

    # Flush and close all
    exp_bands = None

    out_src.close()
    out_src = None
