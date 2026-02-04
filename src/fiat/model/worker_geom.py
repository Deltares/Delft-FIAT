"""Worker function for the geometry model (no csv)."""

import importlib
from math import nan
from multiprocessing.queues import Queue
from multiprocessing.synchronize import Lock
from pathlib import Path
from typing import Callable

from osgeo import ogr

from fiat.fio import (
    BufferedGeomWriter,
    GeomIO,
    GridIO,
)
from fiat.gis import overlay
from fiat.method.ead import fn_ead
from fiat.struct import Table
from fiat.struct.container import ExposureGeomMeta, HazardMeta, VulnerabilityMeta
from fiat.typing import MethodsProtocol

process_lock = None


def initialize_pool(
    lock: Lock,
    queue: Queue,
):
    """Small initializer for the multiprocessing pool."""
    global process_lock
    process_lock = lock
    global pipeline
    pipeline = queue


def feature_worker(
    ft: ogr.Feature,
    hazard: GridIO,
    hazard_meta: HazardMeta,
    vulnerability: Table,
    vulnerability_meta: VulnerabilityMeta,
    exposure_meta: ExposureGeomMeta,
    fn_hazard: Callable,
    fn_impact: Callable,
) -> list[float]:
    """Calculate the impact per feature.

    Parameters
    ----------
    ft : ogr.Feature
        The feature.
    hazard : GridIO
        The hazard data.
    hazard_meta : HazardMeta
        Metadata specific to the hazard data.
    vulnerability : Table
        The vulnerability data.
    vulnerability_meta : VulnerabilityMeta
        Metadata specific to the vulnerability data.
    exposure_meta : ExposureGeomMeta
        Metadata specific to the exposure data.
    fn_hazard : Callable
        The hazard function.
    fn_impact : Callable
        The impact function.

    Returns
    -------
    list[float]
        Array containing the impact values for a feature.
    """
    # The output array
    out_array = []
    haz_args = [ft.GetField(idx) for idx in exposure_meta.indices_spec]

    # Go through the hazard data
    for band in hazard:
        # Get the hazard values
        haz = overlay.clip(
            ft,
            band,
            hazard.geotransform,
        )
        haz[haz == band.nodata] = nan
        haz, fact = fn_hazard(
            haz.tolist(),
            *haz_args,
        )
        out_array += [haz]
        for item in exposure_meta.indices_type.values():
            out_array += fn_impact(
                ft,
                haz,
                fact,
                item,
                vulnerability,
                vulnerability_meta.min,
                vulnerability_meta.max,
                vulnerability_meta.sigdec,
            )

    # Process the results to ead when risk mode
    if hazard_meta.risk:
        i = 0
        for ti in exposure_meta.indices_total:
            ead = round(
                fn_ead(
                    hazard_meta.density, out_array[ti - i :: -exposure_meta.type_length]
                ),
                vulnerability_meta.sigdec,
            )
            out_array.append(ead)
            i += 1

    return out_array


def worker(
    output_dir: Path,
    hazard: GridIO,
    hazard_meta: HazardMeta,
    vulnerability: Table,
    vulnerability_meta: VulnerabilityMeta,
    exposure: GeomIO,
    exposure_meta: ExposureGeomMeta,
    chunk: tuple | list,
):
    """Run the geometry model.

    This is the worker function corresponding to the run method \
of the [GeomModel](/api/GeomModel.qmd) object.

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
    exposure : GeomIO
        The exposure geometries.
    exposure_meta : ExposureGeomMeta
        Metadata specific to the exposure data.
    chunk : tuple | list
        The chunk to run through.
    queue : Queue
        A Queue for logging back to the main thread.
    lock : Lock
        The lock for the geometries output.
    """
    # Setup the hazard type method
    method: MethodsProtocol = importlib.import_module(f"fiat.method.{hazard_meta.type}")
    fn_hazard = method.fn_hazard
    fn_impact = method.fn_impact

    # Setup the dataset buffer writer
    writer = BufferedGeomWriter(
        Path(output_dir, f"{exposure.path.stem}.gpkg"),
        lock=process_lock,
    )
    writer.setup(
        defn=exposure.layer.defn,
        srs=exposure.srs,
        extra_fields=zip(exposure_meta.new, [ogr.OFTReal] * len(exposure_meta.new)),
    )

    # Loop over all the geometries in a reduced manner
    for ft in exposure.layer.reduced_iter(*chunk):
        out_array = feature_worker(
            ft=ft,
            hazard=hazard,
            hazard_meta=hazard_meta,
            vulnerability=vulnerability,
            vulnerability_meta=vulnerability_meta,
            exposure_meta=exposure_meta,
            fn_hazard=fn_hazard,
            fn_impact=fn_impact,
        )

        # Write the feature to the in memory dataset
        writer.add_feature_with_map(
            ft,
            zip(
                exposure_meta.indices_new,
                out_array,
            ),
        )

    writer.close()
    writer = None
