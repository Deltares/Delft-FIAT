"""This tests the FIAT model."""
from delft_fiat.cfg import ConfigReader

from delft_fiat.io import open_geom, open_grid, open_csv
from delft_fiat.gis import overlay
from delft_fiat.models.calc import get_inundation_depth, get_damage_factor

import time
from pathlib import Path


def test_FIAT_vector():
    config_file = Path().absolute() / "tmp" / "Casus" / "settings.toml"
    config = ConfigReader(config_file)

    # Load the input data.
    geoms = open_geom(config.get_path("exposure", "geom_file"))
    hazard = open_grid(config.get_path("hazard", "grid_file"))
    exposure = open_csv(config.get_path("exposure", "dbase_file"))
    vulnerability = open_csv(config.get_path("vulnerability", "dbase_file"))

    # Upscale the vulnerability data
    vulnerability.upscale(0.01)

    # Loop over the exposure objects and time it.
    s = time.time()
    for feature in geoms:
        # Get the hazard values per feature in the exposure data
        hazard_values = overlay.clip(hazard.src, hazard.src.GetRasterBand(1), feature)

        # Get the feature data to calculate inundation depth.
        feature_data = exposure.select(feature.GetField(1))
        hazard_reference = config["hazard"]["spatial_reference"]
        ground_floor_height = float(
            feature_data[exposure.hdr_index["Ground Floor Height"]]
        )

        # Get all damage functions that should be iterated over
        damage_function_categories = [
            c for c in exposure.hdrs if c.startswith("Damage Function:")
        ]

        for dfc in damage_function_categories:
            method_areal_objects = (
                "mean"  # TODO: get from vulnerability_curves.csv meta data
            )

            # Calculate the hazard value with which the damage is calculated and
            # calculate the reduction factor.
            hazard_value, reduction_factor = get_inundation_depth(
                hazard_values=hazard_values,
                hazard_reference=hazard_reference,
                ground_floor_height=ground_floor_height,
                method_areal_objects=method_areal_objects,
            )

            # Find the right damage function values and fractions for the feature.
            damage_function_name = feature_data[exposure.hdr_index[dfc]]
            df_hazard_values = vulnerability.data[list(vulnerability.data.keys())[0]]
            df_fractions = vulnerability.data[damage_function_name]

            # Calculate the damage
            get_damage_factor(
                object_id=exposure.hdr_index["Object ID"],
                hazard_value=hazard_value,
                damage_function_values=df_hazard_values,
                damage_function_fractions=df_fractions,
            )

    el = time.time() - s
    print(f"{el} seconds!")
    pass
