"""Worker function for the geometry model (no csv)."""

import importlib
from math import nan
from multiprocessing.queues import Queue
from multiprocessing.synchronize import Lock
from pathlib import Path

from osgeo import ogr

from fiat.fio import (
    BufferedGeomWriter,
    GeomIO,
    GridIO,
)
from fiat.gis import overlay
from fiat.methods.ead import calculate_ead, risk_density
from fiat.struct import FieldMeta, Table
from fiat.util import deter_dec


def worker(
    cfg: dict,
    risk: bool,
    hazard: GridIO,
    vulnerability: Table,
    exposure: GeomIO,
    exposure_meta: FieldMeta,
    chunk: tuple | list,
    queue: Queue,
    lock: Lock,
):
    """Run the geometry model.

    This is the worker function corresponding to the run method \
of the [GeomModel](/api/GeomModel.qmd) object.

    Parameters
    ----------
    cfg : dict
        The configurations.
    risk : bool
        Whether to run in risk-mode.
    hazard : GridIO
        The hazard data.
    vulnerability : Table
        The vulnerability data.
    exposure : GeomIO
        The exposure geometries.
    exposure_meta : FieldMeta
        Metadata specific to the exposure data.
    chunk : tuple | list
        The chunk to run through.
    queue : Queue
        A Queue for logging back to the main thread.
    lock : Lock
        The lock for the geometries output.
    """
    # Setup the hazard type module
    module = importlib.import_module(f"fiat.methods.{cfg.get('hazard.type')}")
    func_hazard = getattr(module, "calculate_hazard")
    func_damage = getattr(module, "calculate_damage")
    man_columns = getattr(module, "MANDATORY_COLUMNS")
    # Get index for the mandatory columns
    man_columns_idxs = [exposure.layer.fields.index(item) for item in man_columns]

    # Vulnerability metadata
    rounding = deter_dec(cfg.get("vulnerability.step_size"))
    vul_min = min(vulnerability.index)
    vul_max = max(vulnerability.index)

    # Set up info for risk
    if risk:
        rp_coef = risk_density(cfg.get("hazard.return_periods"))
        rp_coef.reverse()

    # Setup the dataset buffer writer
    writer = BufferedGeomWriter(
        Path(cfg.get("output.path"), f"{exposure.path.stem}.gpkg"),
        lock=lock,
    )
    writer.setup(
        defn=exposure.layer.defn,
        srs=exposure.srs,
        extra_fields=zip(exposure_meta.new, [ogr.OFTReal] * len(exposure_meta.new)),
    )

    # Loop over all the geometries in a reduced manner
    for ft in exposure.layer.reduced_iter(*chunk):
        out = []
        haz_kwargs = [ft.GetField(idx) for idx in man_columns_idxs]

        # Go through the hazard data
        for band in hazard:
            # Get the hazard values
            haz = overlay.clip(
                ft,
                band,
                hazard.geotransform,
            )
            haz[haz == band.nodata] = nan
            haz, fact = func_hazard(
                haz.tolist(),
                *haz_kwargs,
            )
            out += [haz]
            for _, item in exposure_meta.types.items():
                out += func_damage(
                    haz,
                    fact,
                    ft,
                    item,
                    vulnerability,
                    vul_min,
                    vul_max,
                    rounding,
                )

        # At last do (if set) risk calculation
        if risk:
            i = 0
            for ti in exposure_meta.total:
                ead = round(
                    calculate_ead(rp_coef, out[ti - i :: -exposure_meta.length]),
                    rounding,
                )
                out.append(ead)
                i += 1

        # Write the feature to the in memory dataset
        writer.add_feature_with_map(
            ft,
            zip(
                exposure_meta.indices,
                out,
            ),
        )

    writer.close()
    writer = None
