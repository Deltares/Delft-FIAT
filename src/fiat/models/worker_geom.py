"""Worker function for the geometry model (no csv)."""

import importlib
from math import nan
from multiprocessing.queues import Queue
from multiprocessing.synchronize import Lock
from pathlib import Path

from fiat.gis import geom, overlay
from fiat.io import BufferedGeomWriter, GridSource, Table


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
    bands = [haz[idx + 1] for idx in range(haz.size)]

    # More meta data
    new = cfg.get("_.new_fields")
    ref = cfg.get("hazard.elevation_reference")
    rounding = cfg.get("vulnerability.round")
    slen = cfg.get("_.csv.slen")
    types = cfg.get("exposure.types")
    vul_min = min(vul.index)
    vul_max = max(vul.index)

    # Loop through the different files
    for file, gm in exp_geom.items():
        # Check if there actually is data for this chunk
        if chunk[0] > gm._count:
            continue

        # Setup the dataset buffer writer
        out_geom = Path(cfg.get(f"output.geom.name{file[-1]}"))
        out_writer = BufferedGeomWriter(
            Path(cfg.get("output.path"), out_geom),
            gm.get_srs(),
            gm.layer.GetLayerDefn(),
            buffer_size=cfg.get("output.geom.settings.chunk"),
            lock=lock,
        )
        out_writer.create_fields(zip(new, [2] * len(new)))

        # Setup indices
        new_idx = list(range(len(gm.fields), len(gm.fields) + slen))

        # Loop over all the geometries in a reduced manner
        for ft in gm.reduced_iter(*chunk):
            for band in bands:
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

                for key, item in types.items():
                    out = func_damage(
                        haz_value,
                        red_fact,
                        ft,
                        item,
                        vul,
                        vul_min,
                        vul_max,
                        rounding,
                    )
                    out_writer.add_feature_with_map(
                        ft,
                        zip(
                            new_idx,
                            [haz_value, red_fact, *out],
                        ),
                    )

                    pass
                pass
        out_writer.close()
        out_writer = None
    pass
