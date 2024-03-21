from pathlib import Path

from fiat.io import BufferedGeomWriter, BufferedTextWriter


def test_bufferedgeom(tmpdir, geom_data):
    out_path = Path(str(tmpdir))
    writer = BufferedGeomWriter(
        Path(out_path, "bufferedgeoms.gpkg"),
        geom_data.get_srs(),
        geom_data.layer.GetLayerDefn(),
        buffer_size=2,
    )
    assert writer.size == 0

    writer.add_feature(
        geom_data.layer.GetFeature(1),
        {},
    )
    assert writer.size == 1

    writer.add_feature(
        geom_data.layer.GetFeature(2),
        {},
    )
    assert writer.size == 2

    writer.add_feature(
        geom_data.layer.GetFeature(3),
        {},
    )
    assert writer.size == 1

    writer.close()
    pass


def test_bufferedtext(tmpdir):
    out_path = Path(str(tmpdir))
    writer = BufferedTextWriter(
        Path(out_path, "bufferedtext.txt"),
        mode="wb",
        buffer_size=15,  # 15 bytes (15 chars)
    )

    writer.write(b"Hello there\n")
    assert writer.tell() == 12

    writer.write(b"Another line\n")
    assert writer.tell() == 13
    writer.seek(0)
    assert writer.read() == b"Another line\n"

    writer.close()

    with open(Path(out_path, "bufferedtext.txt"), "r") as reader:
        text = reader.read()

    assert len(text) == 25
