"""
Bound the number of media requests a worker process handles at once.

A page listing hundreds of shots asks for hundreds of thumbnails in one
burst, all multiplexed on a single HTTP/2 connection. Each one costs a
JWT check, several permission lookups and a storage read: under gevent,
every request in the burst runs at once, and the rest of the API waits
behind them for the CPU and the database pool. A media request now waits
for one of a fixed number of slots first; the other routes never wait.

The slot is held from routing until the view returns its response, so it
covers the permission checks and the cache fill of a picture, not the
streaming of the body that follows. Under the gevent worker the
semaphore is cooperative: gunicorn's config monkey patches threading
before the app is built.
"""

import threading

from flask import g, jsonify, request

MEDIA_PATH_PREFIXES = ("/pictures/", "/movies/")
MEDIA_METHODS = ("GET", "HEAD")
RETRY_AFTER = 5


def is_media_request():
    """
    Whether the current request downloads a picture or a movie. Uploads
    are left out: a slow client upload would hold a slot for its whole
    duration.
    """
    return request.method in MEDIA_METHODS and request.path.startswith(
        MEDIA_PATH_PREFIXES
    )


def media_busy_response():
    """
    The answer for a media request that found no free slot in time: the
    client is told to come back, and nothing caches the refusal.
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
    Let at most `limit` media requests of this process run at once. A
    request waits up to `wait_timeout` seconds for a slot (0 waits as
    long as it takes), then gets a 503. A `limit` of 0 disables the
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
