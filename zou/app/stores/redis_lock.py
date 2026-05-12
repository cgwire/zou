"""
Redis-based distributed lock: thin wrapper around redis-py's native Lock.
"""

import redis
from contextlib import contextmanager

from zou.app import config


def get_redis_client():
    """Redis client for locking; same config as cache. Returns None if Redis unavailable."""
    try:
        client = redis.StrictRedis(
            host=config.KEY_VALUE_STORE["host"],
            port=config.KEY_VALUE_STORE["port"],
            db=config.MEMOIZE_DB_INDEX,
            password=config.KEY_VALUE_STORE["password"],
            decode_responses=True,
        )
        client.ping()
        return client
    except (redis.ConnectionError, redis.TimeoutError, Exception):
        return None


@contextmanager
def with_lock(lock_key, timeout=30, wait_timeout=35):
    """
    Context manager: acquire a Redis lock by key, yield, then release.
    Yields True if lock was acquired, False if Redis unavailable or lock
    not acquired in time.
    """
    client = get_redis_client()
    if client is None:
        yield False
        return
    lock = client.lock(lock_key, timeout=timeout, blocking_timeout=wait_timeout)
    acquired = lock.acquire()
    try:
        yield acquired
    finally:
        if acquired:
            try:
                lock.release()
            except redis.exceptions.LockError:
                pass


@contextmanager
def with_playlist_lock(playlist_id, timeout=30, wait_timeout=35):
    """
    Context manager: acquire playlist lock, yield, then release.
    Yields True if lock was acquired, False if Redis unavailable or lock not acquired in time.
    """
    with with_lock(
        f"playlist_lock:{playlist_id}", timeout, wait_timeout
    ) as acquired:
        yield acquired


@contextmanager
def with_preview_file_lock(preview_file_id, timeout=30, wait_timeout=35):
    """
    Context manager: acquire lock for preview file (e.g. annotation changes), yield, then release.
    Yields True if lock was acquired, False if Redis unavailable or lock not acquired in time.
    """
    with with_lock(
        f"preview_file_annotations_lock:{preview_file_id}",
        timeout,
        wait_timeout,
    ) as acquired:
        yield acquired
