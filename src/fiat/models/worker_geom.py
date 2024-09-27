"""Worker function for the geometry model (no csv)."""

from math import nan
from multiprocessing.queues import Queue
from multiprocessing.synchronize import Lock

from fiat.gis import geom, overlay
from fiat.io import GridSource, Table


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
    # Get the bands to prevent object creation while looping
    bands = [haz[idx + 1] for idx in range(haz.size)]

    # Loop through the different files
    for _, gm in exp_geom.items():
        # Check if there actually is data for this chunk
        if chunk[0] > gm._count:
            continue

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
                pass
    pass
