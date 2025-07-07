import threading
from multiprocessing.queues import Queue

import pytest

from fiat.log.handler import StreamHandler
from fiat.log.thread import Receiver, Sender, _destruct_receivers, _receivers
from fiat.log.util import LogItem


def test_receiver(
    mp_queue: Queue,
):
    # Create the object
    r = Receiver(mp_queue)

    # Assert some simple stuff
    assert isinstance(r.q, Queue)
    assert r.count == 0
    # Important the sentinel message
    assert r._sentinel is None
    # No thread yet
    assert r._t is None


def test_receiver_start(
    mp_queue: Queue,
):
    # Create the object
    r = Receiver(mp_queue)

    # Start the receiver
    r.start()

    # Assert there is a thread
    assert isinstance(r._t, threading.Thread)
    assert r._t.name == "mp_logging_thread"


def test_receiver_handler(
    mp_queue: Queue,
    log_item: LogItem,
    stream_capture: StreamHandler,
):
    # Create the object
    r = Receiver(mp_queue)
    # Add handler
    r.add_handler(stream_capture)

    # Start the stream
    r.start()

    # Put a message in the queue
    mp_queue.put_nowait(log_item)

    # Assert the output, close to force the separate thread to act
    r.close()
    stream_capture.stream.seek(0)
    assert "A logging message" in stream_capture.stream.read()


def test_receiver_close(
    mp_queue: Queue,
    stream_capture: StreamHandler,
):
    # Create the object
    r = Receiver(mp_queue)
    # Add handler
    r.add_handler(stream_capture)

    # Start the receiver
    r.start()

    # Assert current state
    assert r._name in _receivers
    assert not r.closed
    assert r._t.is_alive()
    assert not r._handlers[0].closed

    # Couple the thread to a var for the alive check
    t = r._t

    # Close the receiver
    r.close()
    r.close_handlers()

    # Assert the state
    assert r._name not in _receivers
    assert r.closed
    assert r._t is None
    assert not t.is_alive()
    assert r._handlers[0].closed


def test_sender(
    mp_queue: Queue,
):
    # Create the object
    s = Sender(mp_queue)

    # Assert simple stuff
    assert isinstance(s.q, Queue)


def test_sender_emit(
    mp_queue: Queue,
    log_item: LogItem,
):
    # Create the object
    s = Sender(mp_queue)

    # Emit a message
    s.emit(log_item)

    # Get it
    msg = mp_queue.get(block=True)
    # Assert the msg
    assert msg.msg == "A logging message"


def test_sender_emit_error(
    mp_queue: Queue,
    log_item: LogItem,
):
    # Create the object
    s = Sender(mp_queue)

    # Emit a message
    s.emit(log_item)
    s.emit(log_item)

    # Max size of the queue is two, which means it should crash
    with pytest.raises(
        BufferError,
        match="Issue with the queue: Full",
    ):
        s.emit(log_item)


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
