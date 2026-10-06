"""Worker function for the geometry model (no csv)."""

import importlib
import math
from multiprocessing.queues import Queue
from multiprocessing.synchronize import Lock
from pathlib import Path
from typing import Callable

import numpy as np

from fiat.container import (
    ExposureGeomMeta,
    HazardMeta,
    RunMeta,
    VulnerabilityMeta,
)
from fiat.driver import FlatGeobufReader, NetcdfReader, fgb
from fiat.driver.fgb import Feature, FlatGeobufWriter
from fiat.gis import overlay
from fiat.method.ead import fn_ead
from fiat.model.geom_util import AREA_METHODS
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
    ft: Feature,
    out_array: np.ndarray,
    run_meta: RunMeta,
    hazard: NetcdfReader,
    hazard_meta: HazardMeta,
    vulnerability_meta: VulnerabilityMeta,
    exposure_meta: ExposureGeomMeta,
    fn_hazard: Callable,
    fn_impact: Callable,
) -> None:
    """Calculate the impact per feature.

    Parameters
    ----------
    ft : Feature
        The feature.
    out_array : np.ndarray
        The array in which to place the runtime values.
    run_meta : RunMeta
        Configurations runtime metadata.
    hazard : NetcdfReader
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
    haz_args = [ft.get_field(idx) for idx in exposure_meta.indices_spec]

    # Mask and window for this feature
    mask, window = AREA_METHODS[exposure_meta.area_method](
        geom=ft.geometry,
        gtf=hazard.profile.transform,
        shape=hazard.profile.shape_xy,
    )

    # Loop through the hazard band combo's
    n = 0
    for idxs in hazard_meta.indices_run:
        haz = [overlay.clip(hazard[idx], mask, window) for idx in idxs]
        haz, fact = fn_hazard(
            *haz,
            *haz_args,
            exposure_meta.zonal_method,
        )
        out_array[0 + n * exposure_meta.type_length] = haz
        for key, value in exposure_meta.indices_type.items():
            tot = 0.0
            for i, (f, m) in enumerate(value):
                curve_id = ft.get_field(f)
                exposure = ft.get_field(m)
                out = 0
                if curve_id and exposure:
                    out = fn_impact(
                        hazard=haz,
                        exposure=exposure,
                        fn_curve=vulnerability_meta.fn[curve_id],  # type: ignore
                        fact=fact,
                    )
                    out = 0 if math.isnan(out) else out
                out_array[exposure_meta.indices_impact[key][n][i]] = out
                tot += out
            out_array[exposure_meta.indices_total[key][n]] = tot
        n += 1

    # Process the results to ead when risk mode
    if run_meta.risk:
        for ti, indices in exposure_meta.indices_total.items():
            ead = fn_ead(
                hazard_meta.density,
                out_array[indices],
            )
            out_array[-1] = ead  # TODO fix single index


def worker(
    output_path: Path,
    run_meta: RunMeta,
    hazard: NetcdfReader,
    hazard_meta: HazardMeta,
    vulnerability_meta: VulnerabilityMeta,
    exposure: FlatGeobufReader,
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
    hazard : NetcdfReader
        The hazard data.
    hazard_meta : HazardMeta
        Metadata specific to the hazard data.
    vulnerability_meta : VulnerabilityMeta
        Metadata specific to the vulnerability data.
    exposure : FlatGeobufReader
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

    # Load the data
    hazard.load()

    # Setup the buffered FlatGeobuf writer (shared body file + finalize by parent)
    profile = exposure.profile
    col_names = list(profile.fields) + list(exposure_meta.new)
    col_types = list(profile.dtypes) + [fgb.CT_DOUBLE] * len(exposure_meta.new)
    out_key = Path(output_path).as_posix()
    writer = FlatGeobufWriter(
        out_key,
        col_names=col_names,
        col_types=col_types,
        geom_type=profile.geom_type,
        name=Path(output_path).stem,
        crs_wkt=profile.crs_wkt,
        crs_org=profile.crs_org,
        crs_code=profile.crs_code,
        lock=process_lock,
    )

    # Loop over all the geometries in a reduced manner
    out_array = np.zeros(exposure_meta.new_length, dtype=np.float32)
    for ft in exposure.reduced_iter(*chunk):
        feature_worker(
            ft=ft,
            out_array=out_array,
            run_meta=run_meta,
            hazard=hazard,
            hazard_meta=hazard_meta,
            vulnerability_meta=vulnerability_meta,
            exposure_meta=exposure_meta,
            fn_hazard=fn_hazard,
            fn_impact=fn_impact,
        )

        # Write the feature (existing attributes + new impact values)
        geom = ft.geometry
        writer.add_feature(
            geom.xy,
            geom.ends,
            geom.parts,
            list(ft.values) + out_array.tolist(),
        )
        # Reset the values
        out_array *= 0

    writer.close()
    # Hand the index records (envelope + body offset) to the parent for finalize.
    pipeline.put((out_key, writer.records))
    writer = None
