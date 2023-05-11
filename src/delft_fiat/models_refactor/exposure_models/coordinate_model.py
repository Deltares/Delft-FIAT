from io import BufferedWriter, BytesIO
from os import write
from pathlib import Path
from typing import Dict, List, cast

from osgeo import gdal, ogr

from delft_fiat.gis import geom, overlay
from delft_fiat.io import GeomSource, open_csv, open_geom
from delft_fiat.models.calc import get_damage_factor, get_inundation_depth
from delft_fiat.models_refactor.exposure_models.base_model import BaseModel
from delft_fiat.models_refactor.types import (
    CSV,
    DamageCurve,
    DamageFunc,
    DamageType,
    ExposureConfig,
    ExposureMap,
)


class CoordinateModel(BaseModel):
    def __init__(self, config: ExposureConfig, srs: str) -> None:
        super().__init__(str(config.get("file")), srs)

        self._exposure: CSV = self._read_exposure(str(config.get("dbase_file")))

        self._damage_categories: List[DamageType] = self._get_damage_categories()

        self.GFH_IDX: int | None = self._exposure.header_index.get(
            "Ground Floor Height"
        )

    def __del__(self) -> None:
        BaseModel.__del__(self)

    def _read_exposure_map(self, path: str) -> ExposureMap:
        try:
            # geom_exposure = open_csv(path, large=True)
            # geom_exposure = tuple(list(geom_exposure.data.keys()))
            geom_exposure: GeomSource = open_geom(path)
            geom_srs = geom_exposure.get_srs()
            if not self.srs.IsSame(geom_srs):
                export_to_wtk = geom_srs.ExportToWkt()
                geom_exposure = geom.reproject(geom_exposure, export_to_wtk)    
            return geom_exposure

        except IOError as ioerr:
            # write to log
            raise IOError(f"Error: could not open file: {str(ioerr)}") from ioerr

    def _read_exposure(self, path: str) -> CSV:
        try:
            return open_csv(path, large=True)
        except IOError as ioerr:
            # write to log
            raise IOError("Error: File does not appear to exist.") from ioerr

    def _get_object_exposure(self, feature: ogr.Feature) -> List[str]:
        return cast(List[str], self._exposure.get(cast(str, feature["Object ID"])))

    def _get_hazard_at_object(
        self, hazard: gdal.Dataset, band_id: int, feature: tuple
    ):
        band: gdal.Band = hazard.GetRasterBand(band_id)
        return overlay.pin(hazard, band, feature)  
    
    def _get_damage_categories(self) -> List[DamageType]:
        headers: List[str] = self._exposure.headers
        return [
            (header, header.replace("Damage Function: ", "Max Potential Damage: "))
            for header in headers
            if header.startswith("Damage Function:")
        ]

    def _get_damage_func(
        self,
        vulnerability: CSV,
        geom_exposure: List[str],
        damage_type: str,
    ) -> DamageFunc:
        damage_idx: int = cast(int, self._exposure.header_index.get(damage_type))
        damage_func: str = geom_exposure[damage_idx]

        if damage_func == "nan":
            return "nan", "None"

        method_idx: int = cast(int, vulnerability.header_index.get(damage_func)) - 1
        method = vulnerability.method[method_idx]

        return damage_func, method

    def _get_damage_curve(self, vulnerability: CSV, damage_func: str) -> DamageCurve:
        damage_func_xlabl: str = list(vulnerability.data.keys())[0]
        damage_func_x = vulnerability.data[damage_func_xlabl]
        damage_func_y = vulnerability.data[damage_func]

        return damage_func_x, damage_func_y

    def _calc_damage(
        self,
        vulnerability: CSV,
        max_damage_type: str,
        damage_func: str,
        geom_exposure: List[str],
        depth: float,
    ) -> float:
        depths, damage_factors = self._get_damage_curve(
            vulnerability=vulnerability, damage_func=damage_func
        )

        damage_factor: float = get_damage_factor(
            haz=depth, values=damage_factors, idx=depths, sig=vulnerability.decimals
        )

        max_damage_idx: int = cast(
            int, self._exposure.header_index.get(max_damage_type)
        )
        damage: float = float(geom_exposure[max_damage_idx]) * damage_factor

        return damage

    def calc_hazard_impact(
        self,
        hazard: gdal.Dataset,
        hazard_ref: str,
        band_id: int,
        vulnerabilities: CSV,
        output_path: Path
    ):
        f = open(output_path.joinpath("output.csv"), "wb")

        writer = BufferedWriter(f, buffer_size=15000)

        writer.write((",".join(self._exposure.headers) + ",Damage" + "\n").encode())

        # f.write((",".join(self._exposure.headers) + ",Damage" + "\n").encode())

        damage: float
        for geom_object in self._exposure_map:
            damage = 0
            geom_exposure: List[str] = self._get_object_exposure(
                feature=geom_object
            )  # geom information

            geometry_test = geom_object.GetGeometryRef()
            *coordinates,_ = geometry_test.GetPoint()
            # coordinates = []
            # for i in range(geometry_test.GetPointCount()):
            #     point = geometry_test.GetPoint(i)
            #     coordinates.append(point)

            geom_depths = self._get_hazard_at_object(
                hazard=hazard, band_id=band_id, feature=tuple(coordinates)
            )  # water depth at geom

            if geom_depths is None:
                continue
            geom_gfh: float = (
                float(geom_exposure[self.GFH_IDX]) if self.GFH_IDX is not None else 0
            )
            # ground floor height

            for damage_type, max_damage_type in self._damage_categories:
                if "nan" in (
                    damage_meta := self._get_damage_func(
                        vulnerability=vulnerabilities,
                        geom_exposure=geom_exposure,
                        damage_type=damage_type,
                    )
                ):  # damage function that corresponds to damage type
                    continue

                damage_func, method = damage_meta
                geom_depth, reduction_factor = get_inundation_depth(
                    haz=geom_depths, ref=hazard_ref, gfh=geom_gfh, method=method
                )  # inundation depth

                if geom_depth <= 0:
                    continue

                damage += self._calc_damage(
                    vulnerability=vulnerabilities,
                    max_damage_type=max_damage_type,
                    damage_func=damage_func,
                    geom_exposure=geom_exposure,
                    depth=geom_depth,
                )
                #  calculate damage per damage function type
            geom_exposure.append(str(damage))

            writestr = ",".join(geom_exposure) + "\n"

            writer.write(writestr.encode())
            # f.write(writestr.encode())

        writer.flush()

        f.close()

