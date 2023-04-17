"""This tests the FIAT model."""
import time
from pathlib import Path

import numpy as np

from delft_fiat.cfg import ConfigReader
from delft_fiat.gis import overlay
from delft_fiat.io import open_csv, open_geom, open_grid
from delft_fiat.models.calc import get_damage_factor, get_inundation_depth


# @pytest.mark.skip(reason="Work in progress")
def test_FIAT_vector():
    config_file = Path().absolute() / "tmp" / "Casus" / "settings.toml"
    config = ConfigReader(config_file)

    # Load the input data.
    geoms = open_geom(config.get_path("exposure.geom_file"))
    hazard = open_grid(config.get_path("hazard.grid_file"))
    exposure = open_csv(config.get_path("exposure.dbase_file"))
    vulnerability = open_csv(config.get_path("vulnerability.dbase_file"))

    # Upscale the vulnerability data
    scale_dfs = 0.001  # TODO: get from settings.toml
    vulnerability.upscale(scale_dfs)

    # Get all damage functions that should be iterated over
    damage_function_categories = [
        (df_col, df_col.replace("Damage Function: ", "Max Potential Damage: "))
        for df_col in exposure.headers
        if df_col.startswith("Damage Function:")
    ]

    # Loop over the exposure objects and time it.
    s = time.time()
    for feature in geoms:
        # Get the hazard values per feature in the exposure data
        hazard_values = overlay.clip(hazard.src, hazard.src.GetRasterBand(1), feature)

        # Get the feature data to calculate inundation depth.
        feature_data = exposure.get(feature["Object_ID"])
        hazard_reference = config["hazard.spatial_reference"]
        ground_floor_height = float(
            feature_data[exposure.header_index["Ground Floor Height"]]
        )

        for dfc, max_damage_col in damage_function_categories:
            method_areal_objects = (
                "mean"  # TODO: get from vulnerability_curves.csv meta data
            )

            # Find the right damage function values and fractions for the feature.
            damage_function_name = feature_data[exposure.header_index[dfc]]
            if damage_function_name == "nan":
                # This feature does not use this type of damage function
                continue
            df_hazard_values = vulnerability.data[list(vulnerability.data.keys())[0]]
            df_fractions = vulnerability.data[damage_function_name]

            # Calculate the hazard value with which the damage is calculated and
            # calculate the reduction factor.
            hazard_value, reduction_factor = get_inundation_depth(
                haz=hazard_values,
                ref=hazard_reference,
                gfh=ground_floor_height,
                method=method_areal_objects,
            )

            # Get the damage factor
            if hazard_value == hazard_value:
                damage_factor = get_damage_factor(
                    # object_id=feature_data[exposure.header_index["Object ID"]],
                    haz=hazard_value,
                    values=df_fractions,
                    idx=df_hazard_values,
                    sig=3,
                )
            else:
                damage_factor = np.nan

            # Calculate the damage
            (float(feature_data[exposure.header_index[max_damage_col]]) * damage_factor)

            # TODO: save the damage to the results.

    el = time.time() - s
    print(f"{el} seconds!")
    pass


test_FIAT_vector()
