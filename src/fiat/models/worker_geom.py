"""Worker function for the geometry model (no csv)."""

import importlib
from math import nan
from multiprocessing.queues import Queue
from multiprocessing.synchronize import Lock
from pathlib import Path

from fiat.fio import (
    BufferedGeomWriter,
    BufferedTextWriter,
    GeomIO,
    GridIO,
)
from fiat.gis import geom, overlay
from fiat.methods.ead import calculate_ead, risk_density
from fiat.models.util import get_field_values
from fiat.struct import Table
from fiat.util import DummyWriter


def worker(
    cfg: dict,
    risk: bool,
    haz: GridIO,
    vul: Table,
    exp_geom: GeomIO,
    idx: int,
    chunk: tuple | list,
    queue: Queue,
    lock1: Lock,
    lock2: Lock,
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
    lock1 : Lock
        The lock for the csv output.
    lock2 : Lock
        The lock for the geometries output.
    """
    # Setup the hazard type module
    module = importlib.import_module(f"fiat.methods.{cfg.get('model.type')}")
    func_hazard = getattr(module, "calculate_hazard")
    func_damage = getattr(module, "calculate_damage")
    man_columns = getattr(module, "MANDATORY_COLUMNS")
    man_entries = getattr(module, "MANDATORY_ENTRIES")

    # More meta data
    cfg_entries = [cfg.get(item) for item in man_entries]
    index_col = cfg.get("exposure.geom.settings.index")
    rounding = cfg.get("vulnerability.round")
    vul_min = min(vul.index)
    vul_max = max(vul.index)

    if risk:
        rp_coef = risk_density(cfg.get("hazard.return_periods"))
        rp_coef.reverse()

    # Some exposure csv dependent data (or not)
    mid = None
    pattern = None

    # Check if there actually is data for this chunk
    if chunk[0] > exp_geom.layer._count:
        return

    # Get the object id column index
    oid = exp_geom.layer.fields.index(index_col)

    # Some meta for the specific geometry file
    field_meta = cfg.get("_exposure_meta")[idx]
    slen = field_meta["slen"]
    total_idx = field_meta["total_idx"]
    types = field_meta["types"]
    idxs = field_meta["idxs"]
    man_columns_idxs = [exp_geom.layer.fields.index(item) for item in man_columns]
    mid = exp_geom.layer.fields.index("extract_method")

    # Setup the dataset buffer writer
    out_geom = Path(cfg.get(f"output.geom.name{idx}"))
    out_writer = BufferedGeomWriter(
        Path(cfg.get("output.path"), out_geom),
        exp_geom.layer.srs,
        buffer_size=cfg.get("model.geom.chunk"),
        lock=lock2,
    )

    # Check for the csv writer
    out_text_writer = DummyWriter()
    out_csv = cfg.get(f"output.csv.name{idx}")
    if out_csv is not None:
        out_text_writer = BufferedTextWriter(
            Path(cfg.get("output.path"), out_csv),
            mode="ab",
            buffer_size=100000,
            lock=lock1,
        )

    # Loop over all the geometries in a reduced manner
    for ft in exp_geom.layer.reduced_iter(*chunk):
        out = []
        in_info, out_info, method, haz_kwargs = get_field_values(
            ft,
            oid,
            mid,
            man_columns_idxs,
            pattern,
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
            for _, item in types.items():
                out += func_damage(
                    haz_value,
                    red_fact,
                    in_info,
                    item,
                    vul,
                    vul_min,
                    vul_max,
                    rounding,
                )

        # At last do (if set) risk calculation
        if risk:
            i = 0
            for ti in total_idx:
                ead = round(
                    calculate_ead(rp_coef, out[ti - i :: -slen]),
                    rounding,
                )
                out.append(ead)
                i += 1

        # Write the feature to the in memory dataset
        out_writer.add_feature_with_map(
            ft,
            zip(
                idxs,
                out,
            ),
        )
        out_text_writer.write_iterable(out_info, out)

    out_writer.close()
    out_writer = None
    out_text_writer.close()
    out_text_writer = None
