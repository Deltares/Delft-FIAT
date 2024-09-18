from fiat.methods.ead import calc_ead, risk_density
from fiat.methods.flood import calculate_hazard


def test_calc_haz():
    dmg, red_f = calculate_hazard(
        [2.5, 5, 10],
        reference="dem",
        ground_flht=1.0,
        ground_elevtn=0,
        method="mean",
    )
    assert int(dmg * 100) == 483
    assert int(red_f) == 1

    dmg, red_f = calculate_hazard(
        [0, 2.5, 5, 10],
        reference="dem",
        ground_flht=1.0,
        ground_elevtn=0,
        method="mean",
    )
    assert int(dmg * 100) == 483
    assert int(red_f * 100) == 75

    dmg, red_f = calculate_hazard(
        [0, 2.5, 5, 10],
        reference="datum",
        ground_flht=1.0,
        ground_elevtn=1.0,
        method="mean",
    )
    assert int(dmg * 100) == 383
    assert int(red_f * 100) == 75

    dmg, red_f = calculate_hazard(
        [0, 1.5, 5, 10],
        reference="datum",
        ground_flht=1.0,
        ground_elevtn=1.0,
        method="mean",
    )
    assert int(dmg * 100) == 350
    assert int(red_f * 100) == 75


def test_calc_risk():
    rps = [1, 2, 5, 25, 50, 100]
    dms = [5, 10, 50, 300, 1200, 3000]

    coef = risk_density(rps)
    ead = calc_ead(coef, dms)

    assert int(round(ead, 1) * 100) == 9850


def test_calc_risk_order():
    rps = [50, 2, 100, 25, 1, 5]
    dms = [1200, 10, 3000, 300, 5, 50]

    coef = risk_density(rps)
    ead = calc_ead(coef, dms)

    assert int(round(ead, 1) * 100) == 9850


def test_calc_risk_one():
    rps = [10]
    dms = [5]

    coef = risk_density(rps)
    ead = calc_ead(coef, dms)

    assert int(ead * 100) == 50
