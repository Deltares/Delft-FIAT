from typing import List, Tuple

from osgeo import gdal, ogr

from delft_fiat.gis import geom, overlay
from delft_fiat.io import GeomSource, GridSource, open_geom
from delft_fiat.models.calc import *
from delft_fiat.models_refactor.model_factory import ModelFactory
from delft_fiat.models_refactor.model_types import CSV, DamageType, ExposureMap


class GeomModel(ModelFactory):
    _method = {
        "area": overlay.clip,
        "average": overlay.pin,
    }

    def __init__(self, path: str) -> None:
        super().__init__(path)

    def __del__(self) -> None:
        ModelFactory.__del__(self)

    def _read_exposure_map(self, path: str) -> ExposureMap:
        geom_exposure: GeomSource = open_geom(path)
        ##checks
        geom_srs = geom_exposure.get_srs()
        if not self.srs.IsSame(geom_srs):
            export_to_wtk = geom_srs.ExportToWkt()
            geom_exposure = geom.reproject(geom_exposure, export_to_wtk)
        return geom_exposure

    def _get_object_exposure(self, exposure: CSV, feature: ogr.Feature) -> List[str]:
        return exposure.get(feature["Object_ID"])

    def _get_hazard_at_object(
        self, hazard: gdal.Dataset, bandId: int, feature: ogr.Feature
    ):
        band: gdal.Band = hazard.GetRasterBand(bandId)
        hazard_level = overlay.clip(hazard, band, feature)  # water depth at geom

        return hazard_level

    def _get_damage_func(self, exposure: CSV, geom_exposure, damage_type: str) -> str:
        damage_idx: int = exposure.header_index.get(damage_type)
        damage_func: str = geom_exposure[damage_idx]

        return damage_func

    def _get_damage_categories(self, headers: List[str]):
        ...

    def _get_damage_curve(
        self, vulnerability: CSV, damage_func: str
    ) -> Tuple[float, float]:
        damage_func_xlabl: str = list(vulnerability.data.keys())[0]
        damage_func_x = vulnerability.data[damage_func_xlabl]
        damage_func_y = vulnerability.data[damage_func]

        return damage_func_x, damage_func_y

    def run(
        self,
        hazard: GridSource,
        exposure: CSV,
        damage_categories: List[DamageType],
        vulnerability: CSV,
    ):
        # Here you could get RasterCount and iterate over all the bands
        raster_data: gdal.Dataset = hazard.src
        bandId: int = 1

        ind_gfh = exposure.header_index.get("Ground Floor Height")  # refactor
        hazard_ref = "dem"  # place in configure file

        for geom_object in self._exposure_map:
            damage: float = 0
            geom_exposure: List[str] = self._get_object_exposure(exposure, geom_object)

            geom_depths = self._get_hazard_at_object(
                raster_data, bandId, geom_object
            )  # water depth at geom

            geom_gfh: float = float(geom_exposure[ind_gfh])  # ground floor height

            for damage_type, max_damage in damage_categories:
                if (
                    damage_func := self._get_damage_func(
                        exposure, geom_exposure, damage_type
                    )
                ) == "nan":
                    continue

                _depth_method_idx: int = vulnerability.header_index.get(damage_type) - 1
                _depth_method = vulnerability.method[_depth_method_idx]

                geom_depth, reduction_factor = get_inundation_depth(
                    haz=geom_depths, ref=hazard_ref, gfh=geom_gfh, method=_depth_method
                )

                if geom_depth <= 0:
                    continue

                depths, damage_factors = self._get_damage_curve(
                    vulnerability, damage_func
                )

                damage_factor: float = get_damage_factor(
                    haz=geom_depth, values=damage_factors, idx=depths, sig=3
                )

                max_damage_idx: int = exposure.header_index.get(max_damage)
                damage += float(geom_features[max_damage_idx]) * damage_factor

            # save damage data
