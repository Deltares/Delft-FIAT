from delft_fiat.gis import geom, overlay
from delft_fiat.io import BufferTextHandler, GeomMemFileHandler, open_csv, open_geom
from delft_fiat.log import spawn_logger
from delft_fiat.models.base import BaseModel
from delft_fiat.models.calc import get_inundation_depth, get_damage_factor
from delft_fiat.util import _pat, replace_empty

import os
import threading
import time
from concurrent.futures import ProcessPoolExecutor, wait, as_completed
from io import BufferedWriter
from math import isnan
from multiprocessing import Lock, Pipe, Process, connection, get_context
from multiprocessing.queues import Queue, SimpleQueue
from pathlib import Path
from quick_queue import QQueue, QJoinableQueue

logger = spawn_logger("fiat.model.geom")


## multiprocessing stuff


class ResultItem:
    def __init__(self, fid: int, oid: object, res_str: str, res_dict: dict):
        """_summary_"""

        self.fid = fid
        self.oid = oid
        self.res_str = res_str
        self.res_dict = res_dict


class StopAlarm:
    def __init__(self):
        self._reader, self._writer = Pipe(duplex=False)

    def close(self):
        self._reader.close()
        self._writer.close()

    def send_sentinel(self):
        self._writer.send_bytes(b"")

    def clear(self):
        while self._reader.poll():
            self._reader.recv_bytes()


def worker(
    result_queue: Queue,
    haz: "GridSource",
    idx: int,
    vul: "Table",
    exp: "TableLazy",
    gm: "GeomSource",
):
    """_summary_"""

    for ft in gm:
        row = b""
        _output = {}

        ft_info = replace_empty(
            _pat.split(exp[ft.GetField(0)]),
        )
        ft_info = [x(y) for x, y in zip(exp.dtypes, ft_info)]

        if ft_info[exp._columns["Extraction Method"]].lower() == "area":
            res = overlay.clip(haz[idx], haz.get_srs(), haz.get_geotransform(), ft)
        else:
            res = overlay.pin(haz[idx], haz.get_geotransform(), geom.point_in_geom(ft))
        inun, redf = get_inundation_depth(
            res,
            "DEM",
            ft_info[exp._columns["Ground Floor Height"]],
        )
        # _output.update(
        #     {"Inundation Depth": inun, "Reduction Factor": redf},
        # )

        for key, col in exp.damage_function.items():
            if isnan(inun) or ft_info[col] == "nan":
                _d = ""
            else:
                _df = vul[round(inun, 2), ft_info[col]]
                _d = _df * ft_info[exp.max_potential_damage[key]] * redf

            _output[exp._extra_columns[key]] = _d
            row += f",{_d}".encode()

        result_queue.put(
            ResultItem(ft.GetFID(), ft.GetField(0), row, _output),
            block=True,
        )


def manager(
    result_queue: Queue,
    alarm: StopAlarm,
    exp: "TableLazy",
    gm: "GeomSource",
    writer: BufferTextHandler,
    geom_writer: GeomMemFileHandler = None,
):
    """_summary_"""

    rr = result_queue._reader
    sr = alarm._reader
    readers = [rr, sr]
    while True:
        mail = connection.wait(readers)
        if rr in mail:
            res = result_queue.get()
            raw_text = exp[res.oid]
            raw_text += res.res_str + b"\r\n"
            writer.write(raw_text)
            geom_writer.write_feature(gm[res.fid], res.res_dict)
        else:
            writer.flush()
            geom_writer.dump2drive()
            return


## Actual model


class GeomModel(BaseModel):
    _method = {
        "area": overlay.clip,
        "centroid": overlay.pin,
    }

    def __init__(
        self,
        cfg: "ConfigReader",
    ):
        """_summary_"""

        super().__init__(cfg)

        self._writer = None

        # Reading the data
        self._read_exposure_data()
        self._read_exposure_geoms()
        self._vulnerability_data.upscale(0.01, inplace=True)

        # Starting the writers
        self._create_writer(
            self._exposure_data.columns,
            self._exposure_data._extra_columns,
        )
        self._create_geom_writer()

        # Starting concurrent stuff
        self._result_queue = QQueue()
        self._alarm = StopAlarm()
        self._manager = threading.Thread(
            target=manager,
            args=(
                self._result_queue,
                self._alarm,
                self._exposure_data,
                self._exposure_geoms["file1"],
                self._writer,
                self._geom_writer,
            ),
            daemon=True,
        )
        self._manager.start()

    def __del__(self):
        BaseModel.__del__(self)

    def _clean_up(self):
        self._managerAlarm.close()
        self._managerAlarm = None
        self._result_queue.close()
        self._result_queue = None
        self._writer.close()
        self._writer = None
        del self._geom_writer

    def _create_writer(
        self,
        cols,
        add_cols,
    ):
        """_summary_"""

        out_csv = "output.csv"
        if "output.csv.name" in self._cfg:
            out_csv = self._cfg["output.csv.name"]

        self._writer = BufferTextHandler(
            Path(self._cfg["output.path"], out_csv),
            buffer_size=100000,
        )

        header = (
            ",".join(cols).encode()
            + b","
            + ",".join(add_cols.values()).encode()
            + b"\r\n"
        )
        self._writer.write(header)

    def _create_geom_writer(self):
        out_geom = "spatial.gpkg"
        if "output.geom.name1" in self._cfg:
            out_geom = self._cfg["output.geom.name1"]

        self._geom_writer = GeomMemFileHandler(
            Path(self._cfg["output.path"], out_geom),
            self.srs,
            self._exposure_geoms["file1"].layer.GetLayerDefn(),
            self._exposure_data._extra_columns_meta,
        )

    def _read_exposure_data(self):
        """_summary_"""

        path = self._cfg.get("exposure.geom.csv")
        logger.info(f"Reading exposure data ('{path.name}')")
        data = open_csv(path, index="Object ID", large=True)
        ##checks
        self._exposure_data = data
        self._exposure_data.search_extra_meta(
            ("Damage Function:", "Max Potential Damage")
        )

    def _read_exposure_geoms(self):
        """_summary_"""

        _d = {}
        _found = [item for item in list(self._cfg) if "exposure.geom.file" in item]
        for file in _found:
            path = self._cfg.get(file)
            logger.info(
                f"Reading exposure geometry '{file.split('.')[-1]}' ('{path.name}')"
            )
            data = open_geom(str(path))
            ##checks
            if not (
                self.srs.IsSame(data.get_srs())
                or self.srs.ExportToWkt() == data.get_srs().ExportToWkt()
            ):
                data = geom.reproject(data, data.get_srs().ExportToWkt())
            _d[file.rsplit(".", 1)[1]] = data
        self._exposure_geoms = _d

    def run(self):
        """_summary_"""

        # out_geom = "spatial.gpkg"
        # if "output.geom.name1" in self._cfg:
        #     out_geom = self._cfg["output.geom.name1"]

        # geom_writer = GeomMemFileHandler(
        #     Path(self._cfg["output.path"], out_geom),
        #     self.srs,
        #     self._exposure_geoms["file1"].layer.GetLayerDefn(),
        #     self._exposure_data._extra_columns_meta,
        # )

        if self._hazard_grid.count > 1:
            pcount = min(os.cpu_count(), self._hazard_grid.count)
            with ProcessPoolExecutor(max_workers=pcount) as Pool:
                for idx in range(self._hazard_grid.count):
                    p = Pool.submit(
                        worker,
                        self._hazard_grid,
                        1,
                        self._vulnerability_data,
                        self._exposure_data,
                        self._exposure_geoms["file1"],
                    )
                for f in as_completed([p]):
                    print(f.result())

        else:
            p = Process(
                target=worker,
                args=(
                    self._result_queue,
                    self._hazard_grid,
                    1,
                    self._vulnerability_data,
                    self._exposure_data,
                    self._exposure_geoms["file1"],
                ),
            )
            p.start()
            p.join()
        self._alarm.send_sentinel()
        self._manager.join()
