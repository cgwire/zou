"""
Redis-based distributed lock: set a key with an identifier, release only if we own it.
"""

import time
import uuid
import redis
from contextlib import contextmanager

from zou.app import config

# Lua script for atomic check-and-delete (kept for atomicity, but non-atomic version would also work)
_RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
end
return 0
"""


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


def acquire_lock(lock_key, timeout=30, wait_timeout=35):
    """
    Acquire a lock for the given key.
    - Value: unique identifier (so we only release our own lock)
    - Lock expires after `timeout` seconds so it can't be held forever.

    Returns (redis_client, key, identifier) or (None, None, None) if Redis unavailable.
    If the lock is held by someone else, waits up to `wait_timeout` seconds then returns (None, None, None).
    """
    client = get_redis_client()
    if client is None:
        return None, None, None

    identifier = str(uuid.uuid4())
    deadline = time.time() + wait_timeout

    while time.time() < deadline:
        if client.set(lock_key, identifier, nx=True, ex=timeout):
            return client, lock_key, identifier
        time.sleep(0.1)

    return None, None, None


def release_lock(client, key, identifier):
    """
    Release the lock only if we still own it (key value == identifier).

    Uses a Lua script to atomically check and delete in a single Redis operation.
    This ensures GET+DEL happens atomically (no other Redis command can interleave).

    Note: A non-atomic version would also work correctly:
        current_value = client.get(key)
        if current_value == identifier:
            client.delete(key)

    The identifier check prevents deleting someone else's lock. Lua just makes it atomic.
    """
    if client is None or key is None or identifier is None:
        return
    try:
        # Atomic: GET + check + DEL all in one Redis operation
        client.eval(_RELEASE_SCRIPT, 1, key, identifier)
    except Exception:
        pass  # Lock will expire on its own


@contextmanager
def with_lock(lock_key, timeout=30, wait_timeout=35):
    """
    Context manager: acquire lock by key, yield, then release.
    Yields True if lock was acquired, False if Redis unavailable or lock not acquired in time.
    """
    client, key, identifier = acquire_lock(lock_key, timeout, wait_timeout)
    if client is None and key is None and identifier is None:
        yield False
        return
    try:
        yield True
    finally:
        release_lock(client, key, identifier)


@contextmanager
def with_playlist_lock(playlist_id, timeout=30, wait_timeout=35):
    """
    Context manager: acquire playlist lock, yield, then release.
    Yields True if lock was acquired, False if Redis unavailable or lock not acquired in time.
    """
    with with_lock(f"playlist_lock:{playlist_id}", timeout, wait_timeout) as acquired:
        yield acquired


@contextmanager
def with_preview_file_lock(preview_file_id, timeout=30, wait_timeout=35):
    """
    Context manager: acquire lock for preview file (e.g. annotation changes), yield, then release.
    Yields True if lock was acquired, False if Redis unavailable or lock not acquired in time.
    """
    with with_lock(
        f"preview_file_annotations_lock:{preview_file_id}", timeout, wait_timeout
    ) as acquired:
        yield acquired