from delft_fiat.io import BufferTextHandler
from delft_fiat.gis import geom, overlay
from delft_fiat.models.calc import calc_haz
from delft_fiat.util import NEWLINE_CHAR, _pat, replace_empty

from math import isnan
from pathlib import Path


def geom_worker(
    cfg: "ConfigReader",
    haz: "GridSource",
    idx: int,
    vul: "Table",
    exp: "TableLazy",
    exp_geom: dict,
):
    """Worker function for the geometry based model calculation to run in parallel

    Parameters
    ----------
    cfg : ConfigReader
        Configuration reader object
    haz : GridSource
        Hazard grid source
    idx : int
        Hazard grid index
    vul : Table
        Vulnerability table
    exp : TableLazy
        Exposure table
    exp_geom : dict
        Exposure geometry
    """

    # Get the elevation reference
    _band_name = cfg["hazard.band_names"][idx - 1]
    _ref = cfg.get("hazard.elevation_reference")
    _rnd = cfg.get("vulnerability.round")
    _weighted = False
    _ups = 1

    # Check if the user wants to use weighted damage
    if "global.weight_upscale" in cfg:
        _ups = cfg.get("global.weight_upscale")

    # Create the output file
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

    # Get the vulnerability index range
    vul_min = min(vul.index)
    vul_max = max(vul.index)

    # Loop over the features
    for _, gm in exp_geom.items():
        for ft in gm:
            row = b""

            # Get the feature information
            ft_info_raw = exp[ft.GetField(0)]
            ft_info = replace_empty(_pat.split(ft_info_raw))
            ft_info = [x(y) for x, y in zip(exp.dtypes, ft_info)]
            row += f"{ft_info[exp.index_col]}".encode()

            # Get the inundation depth and reduction factor
            if ft_info[exp._columns["Extraction Method"]].lower() == "area":
                res = overlay.clip(haz[idx], haz.get_srs(), haz.get_geotransform(), ft)
            else:
                res = overlay.pin(
                    haz[idx], haz.get_geotransform(), geom.point_in_geom(ft)
                )
            inun, redf = calc_haz(
                res,
                _ref,
                ft_info[exp._columns["Ground Floor Height"]],
            )
            row += f",{round(inun, 2)},{round(redf, 2)}".encode()

            # Loop over the damage functions
            _td = 0
            for key, col in exp.damage_function.items():
                if isnan(inun) or ft_info[col] == "nan":
                    _d = "nan"
                else:
                    inun = max(min(vul_max, inun), vul_min)
                    _df = vul[round(inun, _rnd), ft_info[col]]
                    _d = _df * ft_info[exp.max_potential_damage[key]] * redf
                    _d = round(_d, 2)
                    _td += _d

                row += f",{_d}".encode()

            row += f",{round(_td, 2)}".encode()

            # Write the row to the output file
            row += NEWLINE_CHAR.encode()
            writer.write(row)

    # Flush the buffer
    writer.flush()
    writer = None


def grid_worker(
    cfg: "ConfigReader",
):
    """_summary_"""

    raise NotImplementedError("grid_worker is not implemented yet")
