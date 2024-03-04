import copy


def test_tabel(vul_data):
    tb = copy.deepcopy(vul_data)
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


def test_geomsource(geom_data):
    assert geom_data.count == 4
    srs = geom_data.get_srs()
    assert srs.GetAuthorityCode(None) == "4326"


def test_gridsource(grid_event_data):
    srs = grid_event_data.get_srs()
    assert srs.GetAuthorityCode(None) == "4326"
