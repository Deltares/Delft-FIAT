"""EAD (Expected Annual Damages) related functionality."""
import math


def calc_ead(
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


def risk_density(
    rp: list | tuple,
) -> list:
    """Calculate the risk density factors from return periods values.

    Parameters
    ----------
    rp : list | tuple
        A list of return periods.

    Returns
    -------
    list
        List of risk density factors.
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
