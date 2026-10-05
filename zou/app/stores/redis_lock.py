"""
Redis-based distributed lock: thin wrapper around redis-py's native Lock.
"""

import logging
import redis
from contextlib import contextmanager

from zou.app import config
from zou.app.stores import redis_client

logger = logging.getLogger(__name__)


def get_redis_client():
    """
    The shared Redis client of the memoization database, where the locks
    live. Opening a client and pinging it on every lock cost two round
    trips per annotation save; the shared client connects lazily and is
    reused. The tests replace this function with a fake store.
    """
    return redis_client.get_client(config.MEMOIZE_DB_INDEX)


@contextmanager
def with_lock(lock_key, timeout=30, wait_timeout=35):
    """
    Context manager: acquire a Redis lock by key, yield, then release.
    Yields True if the lock was acquired or Redis is unavailable
    (degraded mode: the operation proceeds without distributed
    serialization). Yields False only when Redis is reachable but
    the lock acquisition timed out (genuine contention).
    """
    client = get_redis_client()
    if client is None:
        yield True
        return
    try:
        lock = client.lock(
            lock_key, timeout=timeout, blocking_timeout=wait_timeout
        )
        acquired = lock.acquire()
    except (redis.ConnectionError, redis.TimeoutError):
        # Degraded mode: the operation proceeds without distributed
        # serialization rather than failing on an unreachable Redis.
        logger.warning(f"Redis unreachable, running {lock_key} unlocked.")
        yield True
        return
    try:
        yield acquired
    finally:
        if acquired:
            try:
                lock.release()
            except (redis.exceptions.LockError, redis.ConnectionError):
                pass


@contextmanager
def with_playlist_lock(playlist_id, timeout=30, wait_timeout=35):
    """
    Context manager: acquire playlist lock, yield, then release.
    See `with_lock` for the True/False contract.
    """
    with with_lock(
        f"playlist_lock:{playlist_id}", timeout, wait_timeout
    ) as acquired:
        yield acquired


@contextmanager
def with_preview_file_lock(preview_file_id, timeout=30, wait_timeout=35):
    """
    Context manager: acquire lock for preview file (e.g. annotation
    changes), yield, then release. See `with_lock` for the True/False
    contract.
    """
    with with_lock(
        f"preview_file_annotations_lock:{preview_file_id}",
        timeout,
        wait_timeout,
    ) as acquired:
        yield acquired
