import pytest

from fiat.struct import Container


def test_container_empty():
    # Create the object
    c = Container()

    # Assert some simple attributes
    assert c._base == "ds"
    assert isinstance(c._db, list)
    assert isinstance(c._h, list)
    assert len(c) == 0


def test_container_set():
    # Create the object
    c = Container()

    # Set an element or two
    c.set(2)
    c.set(3)

    # Assert the state
    assert hasattr(c, "ds1")
    assert c.ds1 == 2
    assert len(c._h) == 2
    assert len(c._db) == 2
    assert len(c) == 2


def test_container_set_error():
    # Create the object
    c = Container()

    # By calling setitem directly using a key that is not a string
    with pytest.raises(
        TypeError,
        match="'key' should be of type 'str'",
    ):
        c[2] = 3


def test_container_iter():
    # Create the object
    c = Container()

    # Set an element or two
    c.set(2)
    c.set(3)

    # Assert that it can be iterated over
    assert list(c) == [2, 3]


def test_container_delete():
    # Create the object
    c = Container()

    # Set an element or two
    c.set(2)
    c.set(3)
    # Assert current state
    assert len(c._h) == 2
    assert len(c._db) == 2
    assert hasattr(c, "ds1")
    assert hasattr(c, "ds2")

    # Delete by using the attribute
    c.delete("ds1")
    # Assert the state now
    assert len(c._h) == 1
    assert len(c._db) == 1
    assert not hasattr(c, "ds1")

    # Delete by using the hash of the value
    c.delete(hash(3))
    # Assert the state now
    assert len(c._h) == 0
    assert len(c._db) == 0
    assert not hasattr(c, "ds2")


def test_container_delete_error():
    # Create the object
    c = Container()

    # Delete with an incorrect type as input
    with pytest.raises(
        TypeError,
        match="'key' should either be of type 'int' or 'str'",
    ):
        c.delete({})  # Empty dict is of course stupid, but still


def test_container_clean():
    # Create the object
    c = Container()

    # Set an element or two
    c.set(2)
    c.set(3)
    # Assert current state
    assert len(c._h) == 2
    assert len(c._db) == 2

    # Clean the container
    c.clean()
    # Assert the state now
    assert len(c._h) == 0
    assert len(c._db) == 0
