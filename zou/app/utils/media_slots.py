"""
Limit the number of media requests that a worker process handles at
the same time.

A page that lists hundreds of shots asks for hundreds of thumbnails in
one burst, all multiplexed on a single HTTP/2 connection. Each request
costs a JWT check, some permission queries and a storage read. Under
gevent, all the requests of the burst run at the same time, and the
other API requests wait behind them for the CPU and the database pool.
Thus, a media request first waits for one of a fixed number of slots.
The other routes never wait.

The request holds the slot from the routing until the view returns its
response. Thus, the slot covers the permission checks and the cache fill
of a picture, but not the stream of the body after it. Under the gevent
worker, the semaphore is cooperative: the gunicorn configuration monkey
patches threading before Zou builds the app.
"""

import threading

from flask import g, jsonify, request

MEDIA_PATH_PREFIXES = ("/pictures/", "/movies/")
MEDIA_METHODS = ("GET", "HEAD")
RETRY_AFTER = 5


def is_media_request():
    """
    Tell whether the current request downloads a picture or a movie.
    Uploads are not included: a slow upload from a client would hold a
    slot for its full duration.
    """
    return request.method in MEDIA_METHODS and request.path.startswith(
        MEDIA_PATH_PREFIXES
    )


def media_busy_response():
    """
    Return the answer for a media request that found no free slot in
    time. The answer tells the client to try again later, and nothing
    caches the refusal.
    """
    response = jsonify(
        error=True, message="Too many media requests, retry later."
    )
    response.status_code = 503
    response.headers["Retry-After"] = str(RETRY_AFTER)
    response.cache_control.no_store = True
    return response


def init_media_slots(app, limit, wait_timeout):
    """
    Let at most `limit` media requests of this process run at the same
    time. A request waits up to `wait_timeout` seconds for a slot (0 means
    no time limit), then gets a 503. A `limit` of 0 disables the
    mechanism.
    """
    if limit <= 0:
        return
    slots = threading.BoundedSemaphore(limit)
    timeout = wait_timeout if wait_timeout > 0 else None

    @app.before_request
    def acquire_media_slot():
        if not is_media_request():
            return None
        if not slots.acquire(timeout=timeout):
            return media_busy_response()
        g.media_slot = slots
        return None

    @app.teardown_request
    def release_media_slot(_exception):
        slot = g.pop("media_slot", None)
        if slot is not None:
            slot.release()
