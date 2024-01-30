"""The FIAT model workers."""

from math import floor, isnan, nan
from pathlib import Path

from numpy import full, ravel, unravel_index, where

from fiat.gis import geom, overlay
from fiat.io import BufferTextHandler, GridSource, open_grid
from fiat.log import LogItem, Sender
from fiat.models.calc import calc_haz, calc_risk
from fiat.util import NEWLINE_CHAR, create_windows, regex_pattern, replace_empty


def geom_worker(
    cfg: object,
    queue: object,
    haz: GridSource,
    idx: int,
    vul: object,
    exp: object,
    exp_geom: dict,
):
    """_summary_."""
    # Extract the hazard band as an object
    band = haz[idx]
    # Setup some metadata
    _band_name = cfg["hazard.band_names"][idx - 1]
    _pat = regex_pattern(exp.delimiter)
    _ref = cfg.get("hazard.elevation_reference")
    _rnd = cfg.get("vulnerability.round")
    vul_min = min(vul.index)
    vul_max = max(vul.index)

    # Setup the write and write the header
    writer = BufferTextHandler(
        Path(cfg.get("output.path.tmp"), f"{idx:03d}.dat"),
        buffer_size=100000,
    )
    header = (
        f"{exp.meta['index_name']},".encode()
        + ",".join(exp.create_specific_columns(_band_name)).encode()
        + NEWLINE_CHAR.encode()
    )
    writer.write(header)

    # Setup connection with the main process for missing values:
    _sender = Sender(queue=queue)

    # Loop over all the datasets
    for _, gm in exp_geom.items():
        # Loop over all the geometries
        for ft in gm:
            row = b""

            # Acquire data from exposure database
            ft_info_raw = exp[ft.GetField(0)]
            if ft_info_raw is None:
                _sender.emit(
                    LogItem(
                        2,
                        f"Object with ID: {ft.GetField(0)} -> \
No data found in exposure database",
                    )
                )
                continue
            ft_info = replace_empty(_pat.split(ft_info_raw))
            ft_info = [x(y) for x, y in zip(exp.dtypes, ft_info)]
            row += f"{ft_info[exp.index_col]}".encode()

            # Get the hazard data from the exposure geometrie
            if ft_info[exp._columns["Extraction Method"]].lower() == "area":
                res = overlay.clip(band, haz.get_srs(), haz.get_geotransform(), ft)
            else:
                res = overlay.pin(band, haz.get_geotransform(), geom.point_in_geom(ft))

            res[res == band.nodata] = nan

            # Calculate the inundation
            inun, redf = calc_haz(
                res,
                _ref,
                ft_info[exp._columns["Ground Floor Height"]],
                ft_info[exp._columns["Ground Elevation"]],
            )
            row += f",{round(inun, 2)},{round(redf, 2)}".encode()

            # Calculate the damage per catagory, and in total (_td)
            _td = 0
            for key, col in exp.damage_function.items():
                if isnan(inun) or str(ft_info[col]) == "nan":
                    _d = "nan"
                else:
                    inun = max(min(vul_max, inun), vul_min)
                    _df = vul[round(inun, _rnd), ft_info[col]]
                    _d = _df * ft_info[exp.max_potential_damage[key]] * redf
                    _d = round(_d, 2)
                    _td += _d

                row += f",{_d}".encode()

            row += f",{round(_td, 2)}".encode()

            # Write this to the buffer
            row += NEWLINE_CHAR.encode()
            writer.write(row)

    # Flush the buffer to the drive and close the writer
    writer.flush()
    writer = None


def grid_worker_exact(
    cfg: object,
    haz: GridSource,
    idx: int,
    vul: object,
    exp: GridSource,
):
    """_summary_."""
    # Set some variables for the calculations
    exp_bands = []
    write_bands = []
    exp_nds = []
    dmfs = []
    band_n = ""

    # Check the band names
    if haz.count > 1:
        band_n = "_" + cfg.get("hazard.band_names")[idx - 1]

    # Extract the hazard band as an object
    haz_band = haz[idx]
    # Set the output directory
    _out = cfg.get("output.path")
    if cfg.get("hazard.risk"):
        _out = cfg.get("output.path.risk")

    # Create the outgoing netcdf containing every exposure damages
    out_src = open_grid(
        Path(_out, f"output{band_n}.nc"),
        mode="w",
    )
    out_src.create(
        exp.shape_xy,
        exp.count,
        exp.dtype,
        options=["FORMAT=NC4", "COMPRESS=DEFLATE"],
    )
    out_src.set_srs(exp.get_srs())
    out_src.set_geotransform(exp.get_geotransform())
    # Create the outgoing total damage grid
    td_out = open_grid(
        Path(
            _out,
            f"total_damages{band_n}.nc",
        ),
        mode="w",
    )
    td_out.create(
        exp.shape_xy,
        1,
        exp.dtype,
        options=["FORMAT=NC4", "COMPRESS=DEFLATE"],
    )
    # Set the neccesary attributes
    td_out.set_geotransform(exp.get_geotransform())
    td_out.set_srs(exp.get_srs())
    td_band = td_out[1]
    td_noval = -0.5 * 2**128
    td_band.src.SetNoDataValue(td_noval)

    # Prepare some stuff for looping
    for idx in range(exp.count):
        exp_bands.append(exp[idx + 1])
        write_bands.append(out_src[idx + 1])
        exp_nds.append(exp_bands[idx].nodata)
        write_bands[idx].src.SetNoDataValue(exp_nds[idx])
        dmfs.append(exp_bands[idx].get_metadata_item("damage_function"))

    # Going trough the chunks
    for _w, h_ch in haz_band:
        td_ch = td_band[_w]

        # Per exposure band
        for idx, exp_band in enumerate(exp_bands):
            e_ch = exp_band[_w]

            # See if there is any exposure data
            out_ch = full(e_ch.shape, exp_nds[idx])
            e_ch = ravel(e_ch)
            _coords = where(e_ch != exp_nds[idx])[0]
            if len(_coords) == 0:
                write_bands[idx].src.WriteArray(out_ch, *_w[:2])
                continue

            # See if there is overlap with the hazard data
            e_ch = e_ch[_coords]
            h_1d = ravel(h_ch)
            h_1d = h_1d[_coords]
            _hcoords = where(h_1d != haz_band.nodata)[0]

            if len(_hcoords) == 0:
                write_bands[idx].src.WriteArray(out_ch, *_w[:2])
                continue

            # Do the calculations
            _coords = _coords[_hcoords]
            e_ch = e_ch[_hcoords]
            h_1d = h_1d[_hcoords]
            h_1d = h_1d.clip(min(vul.index), max(vul.index))

            dmm = [vul[round(float(n), 2), dmfs[idx]] for n in h_1d]
            e_ch = e_ch * dmm

            idx2d = unravel_index(_coords, *[exp._chunk])
            out_ch[idx2d] = e_ch

            # Write it to the band in the outgoing file
            write_bands[idx].write_chunk(out_ch, _w[:2])

            # Doing the total damages part
            # Checking whether it has values or not
            td_1d = td_ch[idx2d]
            td_1d[where(td_1d == td_noval)] = 0
            td_1d += e_ch
            td_ch[idx2d] = td_1d

        # Write the total damages chunk
        td_band.write_chunk(td_ch, _w[:2])

    # Flush the cache and dereference
    for _w in write_bands[:]:
        write_bands.remove(_w)
        _w.close()
        _w = None

    # Flush and close all
    exp_bands = None
    td_band.close()
    td_band = None
    td_out = None

    out_src.close()
    out_src = None

    haz_band = None


def grid_worker_loose():
    """_summary_."""
    pass


def grid_worker_risk(
    cfg: object,
    chunk: tuple,
):
    """_summary_."""
    _rp_coef = cfg.get("hazard.rp_coefficients")
    _out = cfg.get("output.path")
    _chunk = [floor(_n / len(_rp_coef)) for _n in chunk]
    td = []
    rp = []

    # TODO this is really fucking bad; fix in the future
    # Read the data from the calculations
    for _name in cfg.get("hazard.band_names"):
        td.append(
            open_grid(
                Path(cfg.get("output.path.risk"), f"total_damages_{_name}.nc"),
                chunk=_chunk,
                mode="r",
            )
        )
        rp.append(
            open_grid(
                Path(cfg.get("output.path.risk"), f"total_damages_{_name}.nc"),
                chunk=_chunk,
                mode="r",
            )
        )

    # Create the estimatied annual damages output file
    exp_bands = {}
    write_bands = []
    exp_nds = []
    ead_src = open_grid(
        Path(_out, "ead.nc"),
        mode="w",
    )
    ead_src.create(
        rp[0].shape_xy,
        rp[0].count,
        rp[0].dtype,
        options=["FORMAT=NC4", "COMPRESS=DEFLATE"],
    )
    ead_src.set_srs(rp[0].get_srs())
    ead_src.set_geotransform(rp[0].get_geotransform())

    # Gather and set information before looping through windows.
    for idx in range(rp[0].count):
        exp_bands[idx] = [obj[idx + 1] for obj in rp]
        write_bands.append(ead_src[idx + 1])
        exp_nds.append(rp[0][idx + 1].nodata)
        write_bands[idx].src.SetNoDataValue(exp_nds[idx])

    # Do the calculation for the EAD
    for idx, rpx in exp_bands.items():
        for _w in create_windows(rp[0].shape, _chunk):
            ead_ch = write_bands[idx][_w]
            # check for one
            d_ch = rpx[0][_w]
            d_1d = ravel(d_ch)
            _coords = where(d_1d != exp_nds[0])[0]

            # Check if something is there
            if len(_coords) == 0:
                continue

            data = [_data[_w] for _data in rpx]
            data = [ravel(_data)[_coords] for _data in data]
            data = calc_risk(_rp_coef, data)
            idx2d = unravel_index(_coords, *[_chunk])
            ead_ch[idx2d] = data
            write_bands[idx].write_chunk(ead_ch, _w[:2])

    rpx = None

    # Do some cleaning
    exp_bands = None
    for _w in write_bands[:]:
        write_bands.remove(_w)
        _w.close()
        _w = None
    ead_src.close()
    ead_src = None

    # Create ead total outgoing dataset
    td_src = open_grid(
        Path(_out, "ead_total.nc"),
        mode="w",
    )
    td_src.create(
        td[0].shape_xy,
        1,
        td[0].dtype,
        options=["FORMAT=NC4", "COMPRESS=DEFLATE"],
    )
    td_src.set_srs(td[0].get_srs())
    td_src.set_geotransform(td[0].get_geotransform())
    td_band = td_src[1]
    td_noval = -0.5 * 2**128
    td_band.src.SetNoDataValue(td_noval)

    # Do the calculations for total damages
    for _w in create_windows(td[0].shape, _chunk):
        # Get the data
        td_ch = td_band[_w]
        data = [_data[1][_w] for _data in td]
        d_1d = ravel(data[0])
        _coords = where(d_1d != td[0][1].nodata)[0]

        # Check whether there is data to begin with
        if len(_coords) == 0:
            continue

        # Get data, calc risk and write it.
        data = [ravel(_i)[_coords] for _i in data]
        data = calc_risk(_rp_coef, data)
        idx2d = unravel_index(_coords, *[_chunk])
        td_ch[idx2d] = data
        td_band.write_chunk(td_ch, _w[:2])

    # Cleaning up afterwards
    td = None
    td_band.close()
    td_band = None
    td_src.close()
    td_src = None
