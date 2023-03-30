import math
import numpy as np
from decimal import Decimal
from typing import Optional


def calculate_coefficients(T):
    """Calculates coefficients used to compute the EAD as a linear function of the known damages
    Args:
        T (list of ints): return periods T1 … Tn for which damages are known
    Returns:
        alpha [list of floats]: coefficients a1, …, an (used to compute the AED as a linear function of the known damages)
    In which D(f) is the damage, D, as a function of the frequency of exceedance, f. In order to compute this EAD,
    function D(f) needs to be known for the entire range of frequencies. Instead, D(f) is only given for the n
    frequencies as mentioned in the table above. So, in order to compute the integral above, some assumptions need
    to be made for function D(h):
    (i)	   For f > f1 the damage is assumed to be equal to 0
    (ii)   For f<fn, the damage is assumed to be equal to Dn
    (iii)  For all other frequencies, the damage is estimated from log-linear interpolation between the known damages and frequencies
    """
    # Step 1: Compute frequencies associated with T-values.
    f = [1 / i for i in T]
    lf = [np.log(1 / i) for i in T]

    # Step 2:
    c = [(1 / (lf[i] - lf[i + 1])) for i in range(len(T[:-1]))]

    # Step 3:
    G = [(f[i] * lf[i] - f[i]) for i in range(len(T))]

    # Step 4:
    a = [
        ((1 + c[i] * lf[i + 1]) * (f[i] - f[i + 1]) + c[i] * (G[i + 1] - G[i]))
        for i in range(len(T[:-1]))
    ]
    b = [
        (c[i] * (G[i] - G[i + 1] + lf[i + 1] * (f[i + 1] - f[i])))
        for i in range(len(T[:-1]))
    ]

    # Step 5:
    if len(T) == 1:
        alpha = f
    else:
        alpha = [
            b[0] if i == 0 else f[i] + a[i - 1] if i == len(T) - 1 else a[i - 1] + b[i]
            for i in range(len(T))
        ]
    return alpha


def get_damage_factor(
    object_id: int,
    hazard_value: float,
    damage_function_values: tuple,
    damage_function_fractions: tuple,
    damage_function_scaling: float,
):
    obj_id = -999
    decimals = abs(Decimal(str(damage_function_scaling)).as_tuple().exponent)

    if math.isnan(hazard_value):
        damage_factor = 0.0

    # Raise a warning if the inundation depth exceeds the range of the damage function values.
    try:
        assert hazard_value >= damage_function_values[0]
        assert hazard_value <= damage_function_values[-1]

    except AssertionError:
        # The inundation depth exceeded the limits of the damage function.
        obj_id = object_id

        if hazard_value < damage_function_values[0]:
            damage_factor = damage_function_fractions[0]
        elif hazard_value > damage_function_values[-1]:
            damage_factor = damage_function_fractions[-1]

    else:
        index = damage_function_values.index(round(hazard_value, decimals))

        try:
            damage_factor = damage_function_fractions[index]
        except IndexError:
            print(
                f"Cannot find an appropriate damage fraction for a water depth of {round(hazard_value, decimals)} for Object ID {obj_id}."
            )

    return damage_factor, obj_id


def damage_calculator():
    _func = {}

    pass


def get_inundation_depth(
    hazard_values: "array",
    hazard_reference: str,
    ground_floor_height: float,
    ground_elevation: Optional[float] = 0,
    method_areal_objects: Optional[str] = "mean",
) -> float:
    """_summary_

    Parameters
    ----------
    hazard_values : numpy.array
        _description_
    hazard_reference : str
        _description_
    ground_floor_height : float
        _description_
    ground_elevation : Optional[float], optional
        _description_, by default 0
    method_areal_objects : Optional[str], optional
        _description_, by default "average"

    Returns
    -------
    float
        _description_
    """
    # This part is specific for flooding hazards.
    # Set the default values
    hazard_value = np.NaN
    reduction_factor = np.NaN

    # Set the negative hazard values to 0.
    hazard_values = np.where(hazard_values <= 0, np.nan, hazard_values)

    if len(hazard_values) > 1:
        number_nan = np.sum(np.isnan(hazard_values))
        if number_nan != len(hazard_values):
            # There are values other than NaN in hazard_values.
            # TODO: delete the .lower() functions when this is done at the start of the model.
            if method_areal_objects.lower() == "mean":
                hazard_value = np.nanmean(hazard_values)
                reduction_factor = (len(hazard_values) - number_nan) / len(
                    hazard_values
                )
            elif method_areal_objects.lower() == "max":
                hazard_value = np.nanmax(hazard_values)
                reduction_factor = 1
            else:
                print(
                    "We should write a check for testing the 'Average or Max Inundation over Areal Objects' column to only contain 'average' or 'max'"
                )
    else:
        hazard_value = hazard_values[0]
        reduction_factor = 1

    if hazard_reference.lower() == "datum":
        # The hazard data is referenced to a Datum (e.g., for flooding this is the water elevation).
        hazard_value = hazard_value - ground_elevation

    # Subtract the Ground Floor Height from the hazard value
    hazard_value = hazard_value - ground_floor_height

    return (hazard_value, reduction_factor)


def risk_calculator():
    pass
