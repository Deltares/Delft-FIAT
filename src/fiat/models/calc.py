"""Logic of FIAT."""

import math

from fiat.util import mean

_inun_calc = {
    "mean": mean,
    "max": max,
}


## Calculates coefficients used to compute the EAD as a linear function of
## the known damages
#    Args:
#        T (list of ints): return periods T1 … Tn for which damages are known
#    Returns:
#        alpha [list of floats]: coefficients a1, …, an (used to compute the AED as
#        a linear function of the known damages)
#    In which D(f) is the damage, D, as a function of the frequency of exceedance, f.
#    In order to compute this EAD, function D(f) needs to be known for
#    the entire range of frequencies. Instead, D(f) is only given for the n
#    frequencies as mentioned in the table above. So, in order to compute the integral
#    above, some assumptions need to be made for function D(h):
#    (i)	   For f > f1 the damage is assumed to be equal to 0
#    (ii)   For f<fn, the damage is assumed to be equal to Dn
#    (iii)  For all other frequencies, the damage is estimated from log-linear
#           interpolation between the known damages and frequencies


def calc_rp_coef(
    rp: list | tuple,
):
    """_summary_.

    Parameters
    ----------
    rp : list | tuple
        _description_

    Returns
    -------
    _type_
        _description_
    """
    # Step 1: Compute frequencies associated with T-values.
    _rp = sorted(rp)
    idxs = [_rp.index(n) for n in rp]
    rp_u = sorted(rp)
    rp_l = len(rp_u)

    f = [1 / n for n in rp_u]
    lf = [math.log(1 / n) for n in rp_u]

    if rp_l == 1:
        return f

    # Step 2:
    c = [(1 / (lf[idx] - lf[idx + 1])) for idx in range(rp_l - 1)]

    # Step 3:
    G = [(f[idx] * lf[idx] - f[idx]) for idx in range(rp_l)]

    # Step 4:
    a = [
        (
            (1 + c[idx] * lf[idx + 1]) * (f[idx] - f[idx + 1])
            + c[idx] * (G[idx + 1] - G[idx])
        )
        for idx in range(rp_l - 1)
    ]
    b = [
        (c[idx] * (G[idx] - G[idx + 1] + lf[idx + 1] * (f[idx + 1] - f[idx])))
        for idx in range(rp_l - 1)
    ]

    # Step 5:
    alpha = [
        b[0]
        if idx == 0
        else f[idx] + a[idx - 1]
        if idx == rp_l - 1
        else a[idx - 1] + b[idx]
        for idx in range(rp_l)
    ]

    return [alpha[idx] for idx in idxs]


def calc_dm_f(
    haz: float,
    idx: tuple,
    values: tuple,
    sig: int,
) -> float:
    """_summary_.

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


def calc_haz(
    haz: list,
    ref: str,
    gfh: float,
    ge: float = 0,
    method: str = "mean",
) -> float:
    """_summary_.

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
    _ge = 0
    if ref.lower() == "datum" and not math.isnan(ge):
        # The hazard data is referenced to a Datum
        # (e.g., for flooding this is the water elevation).
        _ge = ge

    # Remove the negative hazard values to 0.
    raw_l = len(haz)
    haz = [n - _ge for n in haz if (n - _ge) > 0.0001]

    if not haz:
        return math.nan, math.nan

    redf = 1

    if method.lower() == "mean":
        redf = len(haz) / raw_l

    if len(haz) > 1:
        haz = _inun_calc[method.lower()](haz)
    else:
        haz = haz[0]

    # Subtract the Ground Floor Height from the hazard value
    haz = haz - gfh

    return haz, redf


def calc_risk(
    rp_coef: list,
    dms: list,
) -> float:
    """Calculate the EAD (risk).

    From a list of return periods and list of corresponding damages.

    Parameters
    ----------
    rp_coef : list
        List of return period coefficients.
    dms : list
        List of corresponding damages
        (in the same order of the return periods coefficients).

    Returns
    -------
    float
        The Expected Annual Damage (EAD), or risk, as a log-linear integration over the
        return periods.
    """
    # Calculate the EAD
    ead = sum([x * y for x, y in zip(rp_coef, dms)])
    return ead
