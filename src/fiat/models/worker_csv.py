"""Worker functions for the geometry model."""

import importlib
import os
from math import nan
from multiprocessing.synchronize import Lock
from pathlib import Path

from osgeo import osr

from fiat.gis import geom, overlay
from fiat.io import (
    BufferedGeomWriter,
    BufferedTextWriter,
    GridSource,
    open_csv,
)
from fiat.log import LogItem, Sender
from fiat.math.ead import calc_ead
from fiat.util import NEWLINE_CHAR, regex_pattern, replace_empty


def worker_ead(
    cfg: object,
    exp_data: object,
    exp_geom: dict,
    chunk: tuple | list,
    csv_lock: Lock = None,
    geom_lock: Lock = None,
):
    """_summary_."""
    # pid
    os.getpid()

    # Numerical stuff
    risk = cfg.get("hazard.risk")
    rp_coef = cfg.get("hazard.rp_coefficients")
    sig_decimals = cfg.get("vulnerability.round")

    # Set srs as osr object
    srs = osr.SpatialReference()
    srs.SetFromUserInput(cfg.get("global.crs"))

    # Reverse the _rp_coef to let them coincide with the acquired
    # values from the temporary files
    if rp_coef:
        rp_coef.reverse()
    new_cols = cfg.get("output.new_columns")
    slen = cfg.get("output.csv.slen")
    total_idx = cfg.get("output.csv.total_idx")

    # For the temp files
    _files = {}
    _paths = Path(cfg.get("output.tmp.path")).glob("*.dat")

    # Open the temporary files lazy
    for p in sorted(_paths):
        _d = open_csv(p, index=exp_data.meta["index_name"], large=True)
        _files[p.stem] = _d
        _d = None

    # Open stream to output csv file
    writer = BufferedTextWriter(
        Path(cfg.get("output.path"), cfg.get("output.csv.name")),
        mode="ab",
        buffer_size=100000,
        lock=csv_lock,
    )

    # Loop over all the geometry source files
    for key, gm in exp_geom.items():
        # Get output filename
        _add = key[-1]
        out_geom = Path(cfg.get(f"output.geom.name{_add}"))

        # Setup the geometry writer
        geom_writer = BufferedGeomWriter(
            Path(cfg.get("output.path"), out_geom),
            srs,
            gm.layer.GetLayerDefn(),
            buffer_size=cfg.get("output.geom.settings.chunk"),
            lock=geom_lock,
        )
        geom_writer.create_fields(zip(new_cols, ["float"] * len(new_cols)))

        # Loop again over all the geometries
        for ft in gm.reduced_iter(*chunk):
            row = b""

            oid = ft.GetField(0)
            ft_info = exp_data[oid]

            # If no data is found in the temporary files, write None values
            if ft_info is None:
                geom_writer.add_feature(
                    ft,
                    dict(zip(new_cols, [None] * len(new_cols))),
                )
                row += f"{oid}".encode()
                row += b"," * (len(exp_data.columns) - 1)
                row += NEWLINE_CHAR.encode()
                writer.write(row)
                continue

            row += ft_info.strip()
            vals = []

            # Loop over all the temporary files (loaded) to
            # get the damage per object
            for item in _files.values():
                row += b","
                _data = item[oid].strip().split(b",", 1)[1]
                row += _data
                _val = [float(num.decode()) for num in _data.split(b",")]
                vals += _val

            if risk:
                for idx in total_idx:
                    ead = round(
                        calc_ead(rp_coef, vals[idx::-slen]),
                        sig_decimals,
                    )
                    row += f",{ead}".encode()
                    vals.append(ead)
            row += NEWLINE_CHAR.encode()
            writer.write(row)
            geom_writer.add_feature(
                ft,
                dict(zip(new_cols, vals)),
            )

        geom_writer.to_drive()
        geom_writer = None

    writer.to_drive()
    writer = None

    # Clean up gdal objects
    srs = None

    # Clean up the opened temporary files
    for _d in _files.keys():
        _files[_d] = None
    _files = None


def worker(
    cfg: object,
    queue: object,
    haz: GridSource,
    idx: int,
    vul: object,
    exp_data: object,
    exp_geom: dict,
    chunk: tuple | list,
    lock: Lock = None,
):
    """_summary_."""
    # Setup the hazard type module
    module = importlib.import_module(f"fiat.math.{cfg.get('global.type')}")
    func_hazard = getattr(module, "calculate_hazard")
    func_damage = getattr(module, "calculate_damage")
    types = cfg.get("exposure.types")

    # Extract the hazard band as an object
    band = haz[idx]

    # Setup some metadata
    pattern = regex_pattern(exp_data.delimiter)
    ref = cfg.get("hazard.elevation_reference")
    rounding = cfg.get("vulnerability.round")
    vul_min = min(vul.index)
    vul_max = max(vul.index)

    # Setup the write and write the header
    writer = BufferedTextWriter(
        Path(cfg.get("output.tmp.path"), f"{idx:03d}.dat"),
        mode="ab",
        buffer_size=100000,
        lock=lock,
    )

    # Setup connection with the main process for missing values:
    sender = Sender(queue=queue)

    # Loop over all the datasets
    for _, gm in exp_geom.items():
        # Check if there actually is data for this chunk
        if chunk[0] > gm._count:
            continue

        # Loop over all the geometries in a reduced manner
        for ft in gm.reduced_iter(*chunk):
            row = b""

            # Acquire data from exposure database
            ft_info_raw = exp_data[ft.GetField(0)]
            if ft_info_raw is None:
                sender.emit(
                    LogItem(
                        2,
                        f"Object with ID: {ft.GetField(0)} -> \
No data found in exposure database",
                    )
                )
                continue
            ft_info = replace_empty(pattern.split(ft_info_raw))
            ft_info = [x(y) for x, y in zip(exp_data.dtypes, ft_info)]
            row += f"{ft_info[exp_data.index_col]}".encode()

            # Get the hazard data from the exposure geometrie
            if ft_info[exp_data._columns["extract_method"]].lower() == "area":
                res = overlay.clip(band, haz.get_srs(), haz.get_geotransform(), ft)
            else:
                res = overlay.pin(band, haz.get_geotransform(), geom.point_in_geom(ft))

            res[res == band.nodata] = nan

            # Calculate hazard type specific values
            haz_value, red_fact = func_hazard(
                res.tolist(),
                reference=ref,
                ground_elevtn=ft_info[exp_data._columns["ground_elevtn"]],
                ground_flht=ft_info[exp_data._columns["ground_flht"]],
            )

            row += f",{round(haz_value,2)},{round(red_fact,2)}".encode()
            # Loop through the exposure types
            for key, item in types.items():
                out = func_damage(
                    haz_value,
                    red_fact,
                    ft_info,
                    item,
                    vul,
                    vul_min,
                    vul_max,
                    rounding,
                )

            row += ("," + "{}," * len(out)).format(*out).rstrip(",").encode()

            # Write this to the buffer
            row += NEWLINE_CHAR.encode()
            writer.write(row)

    # Flush the buffer to the drive and close the writer
    writer.to_drive()
    writer = None
