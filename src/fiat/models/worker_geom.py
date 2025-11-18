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
from fiat.gis import geom, overlay
from fiat.methods.ead import calculate_ead, risk_density
from fiat.models.util import get_field_values
from fiat.struct import FieldMeta, Table


def worker(
    cfg: dict,
    risk: bool,
    haz: GridIO,
    vul: Table,
    exp: GeomIO,
    meta: FieldMeta,
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
    haz : GridIO
        The hazard data.
    vul : Table
        The vulnerability data.
    exp : GeomIO
        The exposure geometries.
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
    man_entries = getattr(module, "MANDATORY_ENTRIES")

    # More meta data
    cfg_entries = [cfg.get(item) for item in man_entries]
    rounding = cfg.get("vulnerability.round")
    vul_min = min(vul.index)
    vul_max = max(vul.index)

    if risk:
        rp_coef = risk_density(cfg.get("hazard.return_periods"))
        rp_coef.reverse()

    # Some meta for the specific geometry fil
    man_columns_idxs = [exp.layer.fields.index(item) for item in man_columns]
    mid = exp.layer.fields.index("extract_method")

    # Setup the dataset buffer writer
    writer = BufferedGeomWriter(
        Path(cfg.get("output.path"), f"{exp.path.stem}.fgb"),
        lock=lock,
    )
    writer.setup_layer(
        defn=exp.layer.defn,
        srs=exp.srs,
        flds=zip(meta.new, [ogr.OFTReal] * len(meta.new)),
    )

    # Loop over all the geometries in a reduced manner
    for ft in exp.layer.reduced_iter(*chunk):
        out = []
        method, haz_kwargs = get_field_values(
            ft,
            mid,
            man_columns_idxs,
        )
        for band in haz:
            # How to get the hazard data
            if method == "area":
                res = overlay.clip(
                    ft,
                    band,
                    haz.geotransform,
                )
            else:
                res = overlay.pin(
                    geom.point_in_geom(ft),
                    band,
                    haz.geotransform,
                )

            res[res == band.nodata] = nan

            haz_value, red_fact = func_hazard(
                res.tolist(),
                *cfg_entries,
                *haz_kwargs,
            )
            out += [haz_value, red_fact]
            for _, item in meta.types.items():
                out += func_damage(
                    haz_value,
                    red_fact,
                    ft,
                    item,
                    vul,
                    vul_min,
                    vul_max,
                    rounding,
                )

        # At last do (if set) risk calculation
        if risk:
            i = 0
            for ti in meta.total:
                ead = round(
                    calculate_ead(rp_coef, out[ti - i :: -meta.length]),
                    rounding,
                )
                out.append(ead)
                i += 1

        # Write the feature to the in memory dataset
        writer.add_feature_with_map(
            ft,
            zip(
                meta.indices,
                out,
            ),
        )

    writer.close()
    writer = None
