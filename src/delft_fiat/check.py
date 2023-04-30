import sys
from decimal import Decimal
from pathlib import Path

from osgeo import gdal, osr

from delft_fiat.log import Log
from delft_fiat.util import generic_path_check


def check_config_data(
    cfg: "ConfigReader",
    logger: "Log",
):
    """General checking of the configurations file"""
    for key, item in cfg.values().items():
        if not cfg[key]:
            logging.warning(
                f"{key} is a missing value. Check the configuration file '{config_path}'.\n--------------------The simulation has been stopped.--------------------"
            )
            sys.exit()


def check_crs(crs, crs_type, config_path):
    # Check if all Coordinate Reference Systems are correctly assigned.
    if isinstance(crs, list):
        for c in crs:
            try:
                assert CRS.from_user_input(c)
            except pyproj.exceptions.CRSError as e:
                logging.warning(e)
                logging.warning(
                    f"The Coordinate Reference System (CRS) of the {crs_type} is not correctly assigned. Please add a valid CRS as EPSG/ESRI code or a coordinate system in Well-Known Text (WKT) in the configuration file '{config_path}'.\n--------------------The simulation has been stopped.--------------------"
                )
                sys.exit()
    elif isinstance(crs, str):
        try:
            assert CRS.from_user_input(crs)
        except pyproj.exceptions.CRSError as e:
            logging.warning(e)
            logging.warning(
                f"The Coordinate Reference System (CRS) of the {crs_type} is not correctly assigned. Please add a valid CRS as EPSG/ESRI code or a coordinate system in Well-Known Text (WKT) in the configuration file '{config_path}'.\n--------------------The simulation has been stopped.--------------------"
            )
            sys.exit()


def check_required_columns(df_exposure, exposure_path):
    list_required_columns = [
        "Object ID",
        "Object Name",
        "Primary Object Type",
        "Secondary Object Type",
        "X Coordinate",
        "Y Coordinate",
        "Extraction Method",
        "Damage Function: Structure",
        "Damage Function: Content",
        "Damage Function: Other",
        "First Floor Elevation",
        "Ground Elevation",
        "Max Potential Damage: Structure",
        "Max Potential Damage: Content",
        "Max Potential Damage: Other",
        "Object-Location Shapefile Path",
        "Object-Location Join ID",
        "Join Attribute Field",
    ]
    list_missing = []
    for c in list_required_columns:
        if c not in df_exposure.columns:
            list_missing.append(c)

    if len(list_missing) > 0:
        logging.warning(
            f"The following columns are missing from the exposure data: {list_missing}. Please add those to the exposure data CSV file: {exposure_path}.\n--------------------The simulation has been stopped.--------------------"
        )
        sys.exit()


def check_damage_function_compliance_and_assign_damage_factor(
    damage_function, inundation_depth, object_id
):
    obj_id = -999

    # Raise a warning if the inundation depth exceeds the range of the damage function.
    try:
        assert inundation_depth * 100 >= damage_function[0]
        assert inundation_depth * 100 <= damage_function[1]

    except AssertionError:
        # The inundation depth exceeded the limits of the damage function.
        obj_id = object_id

        if inundation_depth * 100 < damage_function[0]:
            damage_factor = damage_function[2][0]
        elif inundation_depth * 100 > damage_function[1]:
            damage_factor = damage_function[2][-1]

    else:
        index = [i for i in range(damage_function[0], damage_function[1] + 1)].index(
            int(round(Decimal(inundation_depth), 2) * 100)
        )
        # if damage_function[0] < 0:
        #     # The damage fraction was not found because of negative water depths in the damage function.
        #     # Subtract the index range for the negative damage function from the previously calculated index (damage_function[0] is negative)
        #     index = int(index - (damage_function[0] / (damage_function[0] - damage_function[1]) * len(damage_function[2])))

        try:
            damage_factor = damage_function[2][index]
        except IndexError:
            logging.warning(
                f"Cannot find an appropriate damage fraction for a water depth of {round(Decimal(inundation_depth), 2)} for Object ID {obj_id}."
            )

    return damage_factor, obj_id


def report_object_ids_outside_df(
    obj_outside_df_structure, obj_outside_df_content, obj_outside_df_other
):
    list_object_ids_outside_df = list()
    list_object_ids_outside_df.extend(
        list(obj_outside_df_structure)
        + list(obj_outside_df_content)
        + list(obj_outside_df_other)
    )
    list_object_ids_outside_df = list(set(list_object_ids_outside_df))
    list_object_ids_outside_df.remove(-999)
    list_object_ids_outside_df = str(list_object_ids_outside_df)

    logging.info(
        "The inundation depth exceeded the limits of the damage function for the objects with the following Object IDs: {}".format(
            list_object_ids_outside_df
        )
    )


def check_damage_function_ids(
    damage_functions_exposure, damage_functions_config_file, config_path, exposure_path
):
    all_df_exposure = list(
        damage_functions_exposure["Damage Function: Structure"].unique()
    )
    all_df_exposure.extend(
        list(damage_functions_exposure["Damage Function: Content"].unique())
    )
    all_df_exposure.extend(
        list(damage_functions_exposure["Damage Function: Other"].unique())
    )
    set_df_exposure = set([df for df in all_df_exposure if df == df])

    if not len(set_df_exposure) == len(
        set_df_exposure & set(damage_functions_config_file)
    ):
        logging.warning(
            f"Not all damage functions that are in the exposure input file '{exposure_path}' are defined in the configuration file '{config_path}'. Please add the Damage Functions {set_df_exposure - set(damage_functions_config_file)} in the configuration file.\n--------------------The simulation has been stopped.--------------------"
        )
        sys.exit()


def check_uniqueness_object_ids(df_exposure, exposure_path):
    if len(df_exposure.index) != len(df_exposure["Object ID"].unique()):
        logging.warning(
            f"The Object IDs must be unique. Check the exposure input file: {exposure_path}.\n--------------------The simulation has been stopped.--------------------"
        )
        sys.exit()

    if not all(df_exposure["Object-Location Join ID"].isna()):
        for idx, shp_name in (
            df_exposure.loc[~df_exposure["Object-Location Join ID"].isna()]
            .groupby("Object-Location Shapefile Path")
            .size()
            .to_frame()
            .reset_index()
            .iterrows()
        ):
            length_index_shp = len(
                df_exposure.loc[
                    df_exposure["Object-Location Shapefile Path"]
                    == shp_name["Object-Location Shapefile Path"]
                ].index
            )
            length_unique_shp_id = len(
                [
                    n
                    for n in df_exposure.loc[
                        df_exposure["Object-Location Shapefile Path"]
                        == shp_name["Object-Location Shapefile Path"],
                        "Object-Location Join ID",
                    ].unique()
                    if n == n
                ]
            )
            if length_index_shp != length_unique_shp_id:
                logging.warning(
                    f"The Object-Location Join IDs must be unique per linked Shapefile. Check the exposure input file: {exposure_path}.\n--------------------The simulation has been stopped.--------------------"
                )
                sys.exit()


def check_id_column_shapefile(gdf, col_name, shp_path):
    if col_name not in gdf.columns:
        logging.warning(
            f"The Join Attribute Field {col_name} is not found in shapefile: {shp_path}.\n--------------------The simulation has been stopped.--------------------"
        )
        sys.exit()


def check_gdf_z_coord(gdf, name):
    if any(gdf.geometry.values.has_z):
        logging.warning(
            f"The exposure shapefile {name} contains a Z-coordinate. Please supply a Shapefile with only XY coordinates.\n--------------------The simulation has been stopped.--------------------"
        )
        sys.exit()


def check_hazard_projection(hazard_paths, coordinate_systems, config_path):
    if all(str(hp).endswith(".tif") for hp in hazard_paths):
        # The hazard input are geotiff files.
        for h, cs in zip(hazard_paths, coordinate_systems):
            projection_tiff = gdal.Open(str(h)).GetProjection()
            projection_tiff = CRS.from_user_input(projection_tiff)
            if projection_tiff.name != cs.name:
                logging.warning(
                    f"The hazard data {h.name} is in Coordinate System {projection_tiff.name} while the following was specified for this dataset: {cs.name}. The hazard data Coordinate System must be correctly defined in the configuration file {config_path}."
                )


def check_damages_equals_damage_functions(exposure, exposure_path):
    if any(
        exposure["Max Potential Damage: Structure"].isna()
        != exposure["Damage Function: Structure"].isna()
    ):
        logging.warning(
            f"There are objects that contain a structure damage function but not a max potential structure damage, or vice versa. Please check your exposure input file: {exposure_path}"
        )
    if any(
        exposure["Max Potential Damage: Content"].isna()
        != exposure["Damage Function: Content"].isna()
    ):
        logging.warning(
            f"There are objects that contain a content damage function but not a max potential content damage, or vice versa. Please check your exposure input file: {exposure_path}"
        )
    if any(
        exposure["Max Potential Damage: Other"].isna()
        != exposure["Damage Function: Other"].isna()
    ):
        logging.warning(
            f"There are objects that contain an 'other' damage function but not a max potential 'other' damage, or vice versa. Please check your exposure input file: {exposure_path}"
        )


def check_hazard_extent_resolution(list_hazards):
    if len(list_hazards) == 1:
        return True
    check_hazard_extent = [
        gdal.Open(str(haz)).GetGeoTransform() for haz in list_hazards
    ]
    if len(set(check_hazard_extent)) == 1:
        # All hazard have the exact same extents and resolution
        return True
    else:
        return False


def check_exposure_modification(exposure_modification_df, exposure_modification_path):
    if exposure_modification_df.empty:
        logging.warning(
            f"An exposure modification file is submitted but contains no data (except for the header). Please check your exposure modification data ({exposure_modification_path}).\n--------------------The simulation has been stopped.--------------------"
        )
        exit()


def check_shp_paths_and_make_absolute(df_exposure, fiat_input_path):
    for shp_path in (
        df_exposure.loc[:, "Object-Location Shapefile Path"].dropna().unique().tolist()
    ):
        if not Path(shp_path).is_file():
            df_exposure.loc[
                df_exposure["Object-Location Shapefile Path"] == shp_path,
                "Object-Location Shapefile Path",
            ] = str(Path(fiat_input_path).joinpath(shp_path))
        else:
            df_exposure.loc[
                df_exposure["Object-Location Shapefile Path"] == shp_path,
                "Object-Location Shapefile Path",
            ] = shp_path
    return df_exposure


def check_geographic_reference(exposure_df, exposure_path):
    # Conduct a check to guarantee that each object is assigned with either an X and Y coordinate or an object-location file reference.
    x = len(list(exposure_df["X Coordinate"].dropna()))
    y = len(list(exposure_df["Y Coordinate"].dropna()))
    shps = len(list(exposure_df["Object-Location Shapefile Path"].dropna()))

    if x != y:
        logging.warning(
            f"The number of X and Y coordinates are not aligned. Please check the X and Y coordinates in the exposure input file: {exposure_path}.\n--------------------The simulation has been stopped.--------------------"
        )
        exit()
    if x + shps != len(exposure_df.index):
        logging.warning(
            f"Not all objects have X-Y coordinates. Please check the X and Y coordinates in the exposure input file: {exposure_path}.\n--------------------The simulation has been stopped.--------------------"
        )
        exit()


def check_input_data(input_data, exposure_path):
    # Check if all required fields are in the exposure data.
    list_required_fields = [
        "Object ID",
        "Extraction Method",
        "Damage Function: Structure",
        "Damage Function: Content",
        "First Floor Elevation",
        "Ground Elevation",
        "Max Potential Damage: Structure",
        "Max Potential Damage: Content",
    ]
    for fld in list_required_fields:
        try:
            assert fld in input_data["df_exposure"].columns
        except AssertionError:
            logging.warning(
                f"Column {fld} is required and missing from the exposure input file '{exposure_path}'.\n--------------------The simulation has been stopped.--------------------"
            )
            sys.exit()

    # Check if all objects have an extraction method of 'centroid' when not providing a shapefile. If not, set it to centroid.
    df = input_data["df_exposure"].loc[
        (input_data["df_exposure"]["Extraction Method"] == "AREA"),
        ["Object-Location Shapefile Path"],
    ]
    if df["Object-Location Shapefile Path"].isna().any():
        logging.warning(
            "All objects with an 'area' Extraction Method must be linked to a shapefile in the Object-Location Shapefile Path column. The Extraction Method will be set from 'area' to 'centroid' for those objects without an Object-Location Shapefile Path."
        )
        idx_area = (
            input_data["df_exposure"]
            .loc[input_data["df_exposure"]["Extraction Method"] == "AREA"]
            .index
        )
        idx_shp = (
            input_data["df_exposure"]
            .loc[input_data["df_exposure"]["Object-Location Shapefile Path"].isna()]
            .index
        )
        input_data["df_exposure"].loc[
            input_data["df_exposure"].index.isin(list(set(idx_area) & set(idx_shp))),
            "Extraction Method",
        ] = "CENTROID"

    return input_data


def check_lower_case_colnames(data, lowercase_columns, correct_name):
    if correct_name not in data.columns:
        if correct_name.lower() in lowercase_columns:
            idx = lowercase_columns.index(correct_name.lower())
            data.rename(columns={data.columns[idx]: correct_name}, inplace=True)
    return data


def check_correct_columns_names(exposure):
    exposure.columns = [c.title() if "ID" not in c else c for c in exposure.columns]
    lowercase_columns = [c.lower() for c in exposure.columns]
    exposure = check_lower_case_colnames(exposure, lowercase_columns, "Object ID")
    exposure = check_lower_case_colnames(
        exposure, lowercase_columns, "Object-Location Join ID"
    )
    exposure = check_lower_case_colnames(exposure, lowercase_columns, "Buyout (1=yes)")
    exposure = check_lower_case_colnames(
        exposure, lowercase_columns, "Aggregation Variable: SVI"
    )
    return exposure


def check_dem_datum(config_data):
    if len(set(config_data["inundation_references"])) != 1:
        logging.warning(
            f"There may only be one type of 'Inundation Reference' for the flood maps. Please check your configuration file '{config_data['config_path']}'.\n--------------------The simulation has been stopped.--------------------"
        )
        sys.exit()


def check_exposure_within_extent(gdf_exposure):
    if gdf_exposure.empty:
        logging.warning(
            "No exposure objects are within the flood map extent.\n--------------------The simulation has been stopped.--------------------"
        )
        exit()
