from multiprocessing.queues import Queue

from fiat.log.handler import StreamHandler
from fiat.log.thread import LogReceiver
from fiat.log.util import LogItem
from fiat.thread import _receivers


def test_receiver_handler(
    mp_queue: Queue,
    log_item: LogItem,
    stream_capture: StreamHandler,
):
    # Create the object
    r = LogReceiver(mp_queue)
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


def test_log_receiver_close_handlers(
    mp_queue: Queue,
    stream_capture: StreamHandler,
):
    # Create the object
    r = LogReceiver(mp_queue)
    # Add handler
    r.add_handler(stream_capture)

    # Start the receiver
    r.start()

    # Assert current state
    assert r._name in _receivers
    assert not r.closed
    assert not r._handlers[0].closed

    # Close the receiver
    r.close()
    r.close_handlers()

    # Assert the state
    assert r._name not in _receivers
    assert r.closed
    assert r._handlers[0].closed
