import copy


def test_geomsource(geom_data):
    assert geom_data.size == 4
    srs = geom_data.get_srs()
    assert srs.GetAuthorityCode(None) == "4326"


def test_gridsource(grid_event_data):
    srs = grid_event_data.get_srs()
    assert srs.GetAuthorityCode(None) == "4326"


def test_tabel(vul_data):
    tb = copy.deepcopy(vul_data)
    assert len(tb.columns) == 3
    assert len(tb.index) == 21
    assert int(tb[9, "struct_2"] * 100) == 74
    max_idx = max(tb.index)
    assert max_idx == 20

    # interpolate to refine the scale
    tb.upscale(0.01, inplace=True)
    assert len(tb.columns) == 3
    assert len(tb) == 2001
    assert int(tb[9, "struct_2"] * 100) == 74
    assert int(tb[8.99, "struct_2"] * 10000) == 7389
