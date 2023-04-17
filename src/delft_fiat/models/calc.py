import math

from delft_fiat.util import mean

_inun_calc = {
    "mean": mean,
    "max": max,
}


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
    haz: float,
    idx: tuple,
    values: tuple,
    sig: int,
) -> float:
    """_summary_

    Parameters
    ----------
    haz : float
        _description_
    idx : tuple
        _description_
    values : tuple
        _description_
    sig : int
        significant figures

    Returns
    -------
    float
        Damage factor
    """

    if math.isnan(haz):
        return 0.0

    # Clip based on min and max vulnerability values
    haz = max(min(haz, idx[-1]), idx[0])

    return values[idx.index(round(haz, sig))]


def damage_calculator():
    _func = {}

    pass


def get_inundation_depth(
    haz: list, ref: str, gfh: float, ge: float = 0, method: str = "mean"
) -> tuple[float, float]:
    """_summary_

    Parameters
    ----------
    haz : list
        _description_
    ref : str
        _description_
    gfh : float
        _description_
    ge : float, optional
        Ground Elevation, by default 0
    method : str, optional
        _description_, by default "mean"

    Returns
    -------
    float
        _description_
    """

    # Remove the negative hazard values to 0.
    raw_l = len(haz)
    haz = [n for n in haz if n >= 0]

    if not haz:
        return math.nan, math.nan

    redf = 1

    if len(haz) > 1:
        if method.lower() == "mean":
            redf = len(haz) / raw_l
        haz = _inun_calc[method.lower()](haz)
    else:
        haz = haz[0]

    if ref.lower() == "datum":
        # The hazard data is referenced to a Datum (e.g., for flooding this is the water elevation).
        haz = haz - ge

    # Subtract the Ground Floor Height from the hazard value
    haz = haz - gfh

    return haz, redf


def risk_calculator():
    pass
