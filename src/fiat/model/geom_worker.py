"""Worker function for the geometry model (no csv)."""

import importlib
from multiprocessing.queues import Queue
from multiprocessing.synchronize import Lock
from pathlib import Path
from typing import Callable

from osgeo import ogr

from fiat.fio import GeomIO, GridIO
from fiat.gis import overlay
from fiat.method.ead import fn_ead
from fiat.model.geom_writer import GeomWriter
from fiat.struct.container import (
    ExposureGeomMeta,
    HazardMeta,
    RunMeta,
    VulnerabilityMeta,
)
from fiat.typing import MethodType
from fiat.util import FIAT_METHOD

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
    run_meta: RunMeta,
    hazard: GridIO,
    hazard_meta: HazardMeta,
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
    run_meta : RunMeta
        Configurations runtime metadata.
    hazard : GridIO
        The hazard data.
    hazard_meta : HazardMeta
        Metadata specific to the hazard data.
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
    out_array = [0.0] * exposure_meta.new_length
    haz_args = [ft.GetField(idx) for idx in exposure_meta.indices_spec]

    # Mask and window for this feature
    mask, window = overlay.mask(
        geom=ft.GetGeometryRef(),
        gtf=hazard.geotransform,
        shape=hazard.shape_xy,
    )

    # Loop through the hazard band combo's
    n = 0
    for idxs in hazard_meta.indices_run:
        haz = [hazard[idx][*window][mask == 1].tolist() for idx in idxs]
        haz, fact = fn_hazard(
            *haz,
            *haz_args,
            run_meta.zonal_method,
        )
        out_array[0 + n * exposure_meta.type_length] = haz
        for key, value in exposure_meta.indices_type.items():
            tot = 0.0
            for i, (f, m) in enumerate(value):
                curve_id = ft.GetField(f)
                out = 0
                if curve_id is not None:
                    out = fn_impact(
                        hazard=haz,
                        exposure=ft.GetField(m),
                        fn_curve=vulnerability_meta.fn[curve_id],
                        fact=fact,
                    )
                out_array[exposure_meta.indices_impact[key][n][i]] = out
                tot += out
            out_array[exposure_meta.indices_total[key][n]] = tot
        n += 1

    # Process the results to ead when risk mode
    if run_meta.risk:
        i = 0
        for ti, indices in exposure_meta.indices_total.items():
            ead = fn_ead(
                hazard_meta.density,
                out_array[indices[-1] - i :: -exposure_meta.type_length],
            )
            out_array[-1] = ead  # TODO fix single index
            i += 1

    return out_array


def worker(
    output_path: Path,
    run_meta: RunMeta,
    hazard: GridIO,
    hazard_meta: HazardMeta,
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
    output_path : Path
        The path to file to be written.
    run_meta : RunMeta
        The configurations runtime meta.
    hazard : GridIO
        The hazard data.
    hazard_meta : HazardMeta
        Metadata specific to the hazard data.
    vulnerability_meta : VulnerabilityMeta
        Metadata specific to the vulnerability data.
    exposure : GeomIO
        The exposure geometries.
    exposure_meta : ExposureGeomMeta
        Metadata specific to the exposure data.
    chunk : tuple | list
        The chunk to run through.
    """
    # Setup the hazard type method
    method: MethodType = importlib.import_module(f"{FIAT_METHOD}.{run_meta.type}")
    fn_hazard = method.fn_hazard
    fn_impact = method.fn_impact

    # Setup the dataset buffer writer
    writer = GeomWriter(
        output_path,
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
            run_meta=run_meta,
            hazard=hazard,
            hazard_meta=hazard_meta,
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
