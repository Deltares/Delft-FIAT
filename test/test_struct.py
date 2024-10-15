import copy
import math
import pickle


def test_geomsource(geom_data):
    # Do Attribute checks
    assert geom_data.size == 4

    bounds = geom_data.bounds
    bounds = [round(item * 10000) for item in bounds]
    assert bounds == [43550, 44395, 519605, 520450]

    assert geom_data.fields == ["object_id", "object_name"]

    srs = geom_data.get_srs()
    assert srs.GetAuthorityCode(None) == "4326"

    # Stucture should be able to be pickled
    reduced = pickle.dumps(geom_data)
    # Rebuild it
    rebuild = pickle.loads(reduced)
    assert rebuild.size == 4


def test_gridsource(grid_event_data):
    # Do attribute checks
    assert grid_event_data.size == 1

    bounds = grid_event_data.bounds
    bounds = [math.ceil(item * 10000) for item in bounds]
    assert bounds == [43500, 44500, 519500, 520500]

    assert grid_event_data.chunk == (10, 10)
    assert grid_event_data.shape == (10, 10)

    srs = grid_event_data.get_srs()
    assert srs.GetAuthorityCode(None) == "4326"

    # Stucture should be able to be pickled
    reduced = pickle.dumps(grid_event_data)
    # Rebuild it
    rebuild = pickle.loads(reduced)
    assert rebuild.shape == (10, 10)


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

    # Stucture should be able to be pickled
    reduced = pickle.dumps(tb)
    # Rebuild it
    rebuild = pickle.loads(reduced)
    assert int(rebuild[8.99, "struct_2"] * 10000) == 7389
