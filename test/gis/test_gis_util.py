from fiat.gis.util import pixel2world, world2pixel


def test_pixel2world(geotransform: tuple):
    # Call the function
    p = pixel2world(gtf=geotransform, x=9, y=12)

    # Assert the output
    assert p == (4.5, 4.0)

    # Call the function
    p = pixel2world(gtf=geotransform, x=15, y=7)

    # Assert the output
    assert p == (7.5, 6.5)


def test_world2pixel(geotransform: tuple):
    # Call the function
    p = world2pixel(gtf=geotransform, x=3.4, y=7.7)

    # Assert the output
    assert p == (6, 4)

    # Call the function
    p = world2pixel(gtf=geotransform, x=8.6, y=2.2)

    # Assert the output
    assert p == (17, 15)
