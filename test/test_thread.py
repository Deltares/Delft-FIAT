import threading
from multiprocessing.queues import Queue

import pytest

from fiat.thread import Receiver, Sender, _destruct_receivers, _receivers


## Simple function for checking the threading
def worker(*args):
    pass


def test_thread_destruct(
    mp_queue: Queue,
):
    # Create the object
    r = Receiver(mp_queue)
    r2 = Receiver(mp_queue)

    # Assert they are in the receivers weakref dict
    assert r._name in _receivers
    assert r2._name in _receivers

    # Destruct at exit
    _destruct_receivers()

    # Assert they are not longer there
    assert r._name not in _receivers
    assert r2._name not in _receivers

    # Assert they are closed
    assert r.closed
    assert r2.closed


def test_receiver(
    mp_queue: Queue,
):
    # Create the object
    r = Receiver(mp_queue)

    # Assert some simple stuff
    assert isinstance(r.queue, Queue)
    assert r.count == 0
    # Important the sentinel message
    assert r._sentinel is None
    # No thread yet
    assert r.thread is None


def test_receiver_start(
    mp_queue: Queue,
):
    # Create the object
    r = Receiver(mp_queue)

    # Start the receiver
    r.start(
        fn=worker,
        name="log_thread",
    )

    # Assert there is a thread
    assert isinstance(r.thread, threading.Thread)
    assert r.thread.name == "test_receiver"


def test_receiver_start_errors(
    mp_queue: Queue,
):
    # Create the object
    r = Receiver(mp_queue)

    # Start the thread with no known function
    with pytest.raises(
        ValueError,
        match="fn not provided and object fn method not defined.",
    ):
        r.start()


def test_receiver_close(
    mp_queue: Queue,
):
    # Create the object
    r = Receiver(mp_queue)

    # Start the receiver
    r.start(
        fn=worker,
        name="test_receiver",
    )

    # Assert current state
    assert r._name in _receivers
    assert not r.closed
    assert r.thread.is_alive()

    # Couple the thread to a var for the alive check
    t = r.thread

    # Close the receiver
    r.close()

    # Assert the state
    assert r._name not in _receivers
    assert r.closed
    assert r.thread is None
    assert not t.is_alive()


def test_sender(
    mp_queue: Queue,
):
    # Create the object
    s = Sender(mp_queue)

    # Assert simple stuff
    assert isinstance(s.queue, Queue)


def test_sender_emit(
    mp_queue: Queue,
):
    # Create the object
    s = Sender(mp_queue)

    # Emit a message
    s.emit(("foo", "bar"))

    # Get it
    msg = mp_queue.get(block=True)
    # Assert the second item
    assert msg[1] == "bar"


def test_sender_emit_error(
    mp_queue: Queue,
):
    # Create the object
    s = Sender(mp_queue)

    # Emit a message
    s.emit(("foo", "bar"))
    s.emit(("foo", "bar"))

    # Max size of the queue is two, which means it should crash
    with pytest.raises(
        BufferError,
        match="Issue with the queue: Full",
    ):
        s.emit(("foo", "bar"))
