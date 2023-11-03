from fiat.io import open_csv


def test_tabel(cfg_geom_event):
    tb = open_csv(cfg_geom_event.get("vulnerability.file"))
    assert len(tb.columns) == 3
    assert len(tb.index) == 21
    assert tb[9, "struct_2"] == 0.74
    max_idx = max(tb.index)

    # interpolate to refine the scale
    tb.upscale(0.01, inplace=True)
    assert len(tb.columns) == 3
    assert len(tb) == 2001
    assert tb[9, "struct_2"] == 0.74
    assert tb[8.99, "struct_2"] == 0.7389
    assert max(tb.index) == max_idx


def test_geomsource(gm):
    assert gm.count == 4
    srs = gm.get_srs()
    assert srs.GetAuthorityCode(None) == "4326"


def test_gridsource(gr_event):
    srs = gr_event.get_srs()
    assert srs.GetAuthorityCode(None) == "4326"
