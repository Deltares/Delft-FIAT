"""Worker function for the geometry model (no csv)."""

import importlib
from math import nan
from multiprocessing.queues import Queue
from multiprocessing.synchronize import Lock
from pathlib import Path

from fiat.gis import geom, overlay
from fiat.io import BufferedGeomWriter, GridSource, Table
from fiat.methods.ead import calc_ead, risk_density


def worker(
    cfg,
    queue: Queue,
    haz: GridSource,
    vul: Table,
    exp_geom: dict,
    chunk: tuple | list,
    lock: Lock,
):
    """_summary_."""
    # Setup the hazard type module
    module = importlib.import_module(f"fiat.methods.{cfg.get('global.type')}")
    func_hazard = getattr(module, "calculate_hazard")
    func_damage = getattr(module, "calculate_damage_ft")

    # Get the bands to prevent object creation while looping
    bands = [(haz[idx + 1], idx + 1) for idx in range(haz.size)]

    # More meta data
    ref = cfg.get("hazard.elevation_reference")
    risk = cfg.get("hazard.risk", False)
    rounding = cfg.get("vulnerability.round")
    vul_min = min(vul.index)
    vul_max = max(vul.index)

    if risk:
        rp_coef = risk_density(cfg.get("hazard.return_periods"))
        rp_coef.reverse()

    # Loop through the different files
    for idx, gm in exp_geom.items():
        # Check if there actually is data for this chunk
        if chunk[0] > gm._count:
            continue

        # Some meta for the specific geometry file
        field_meta = cfg.get("_exposure_meta")[idx]
        new = field_meta["new_fields"]
        slen = field_meta["slen"]
        total_idx = field_meta["total_idx"]
        types = field_meta["types"]
        idxs = field_meta["idxs"]

        # Setup the dataset buffer writer
        out_geom = Path(cfg.get(f"output.geom.name{idx}"))
        out_writer = BufferedGeomWriter(
            Path(cfg.get("output.path"), out_geom),
            gm.get_srs(),
            gm.layer.GetLayerDefn(),
            buffer_size=cfg.get("output.geom.settings.chunk"),
            lock=lock,
        )
        out_writer.create_fields(zip(new, [2] * len(new)))

        # Loop over all the geometries in a reduced manner
        for ft in gm.reduced_iter(*chunk):
            out = []
            for band, bn in bands:
                # How to get the hazard data
                if ft.GetField("extract_method") == "area":
                    res = overlay.clip(band, haz.get_srs(), haz.get_geotransform(), ft)
                else:
                    res = overlay.pin(
                        band, haz.get_geotransform(), geom.point_in_geom(ft)
                    )

                res[res == band.nodata] = nan

                haz_value, red_fact = func_hazard(
                    res.tolist(),
                    reference=ref,
                    ground_elevtn=ft.GetField(gm._columns["ground_elevtn"]),
                    ground_flht=ft.GetField(gm._columns["ground_flht"]),
                )
                out += [haz_value, red_fact]
                for key, item in types.items():
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
                for ti in total_idx:
                    ead = round(
                        calc_ead(rp_coef, out[ti - i :: -slen]),
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

            pass
        out_writer.close()
        out_writer = None
    pass
