"""
This module is a wrapper for flask_caching. It configures it and renames
the memoize function. The aim of this cache is to decrease the number of
requests to the target database.

SimpleCache (in memory) and Redis both pickle the values, so each hit
is a new copy and callers cannot corrupt the cached objects. With
SimpleCache, a deepcopy wrapper also copies the results.

SQLAlchemy ORM instances come back as they are, without deepcopy: a copy
of their internal InstanceState is not safe and makes objects that
merge() rejects as "dirty". Callers that hold ORM instances must
session.merge() them. This makes a copy that the session owns and does
not change the cached object.
"""

import copy
import logging
import uuid
from functools import wraps

import redis
from flask_caching import Cache

from zou.app import config

logger = logging.getLogger(__name__)

cache = None
_is_simple_cache = False

if config.CACHE_TYPE is not None:
    cache = Cache(config={"CACHE_TYPE": config.CACHE_TYPE})
    _is_simple_cache = config.CACHE_TYPE in ("simple", "SimpleCache")
else:
    try:
        redis_cache = redis.StrictRedis(
            host=config.KEY_VALUE_STORE["host"],
            port=config.KEY_VALUE_STORE["port"],
            db=config.MEMOIZE_DB_INDEX,
            password=config.KEY_VALUE_STORE["password"],
            decode_responses=True,
        )
        redis_cache.get("test")
        cache = Cache(
            config={
                "CACHE_TYPE": "redis",
                "CACHE_REDIS_HOST": config.KEY_VALUE_STORE["host"],
                "CACHE_REDIS_PORT": config.KEY_VALUE_STORE["port"],
                "CACHE_REDIS_DB": config.MEMOIZE_DB_INDEX,
                "CACHE_REDIS_PASSWORD": config.KEY_VALUE_STORE["password"],
            }
        )
    except redis.ConnectionError:
        # SimpleCache is per process: with more than one worker, each
        # worker keeps its own copy, and delete_memoized() only invalidates
        # the local copy. Thus, after a mutation by one worker, the other
        # workers serve stale data until their TTL expires.
        logger.warning(
            "Cache Redis is unreachable, falling back to in-memory "
            "SimpleCache. With multiple workers, cache invalidation is "
            "BROKEN across processes: stale data may be served. Fix the "
            "Redis connection or set CACHE_TYPE explicitly."
        )
        cache = Cache(config={"CACHE_TYPE": "simple"})
        _is_simple_cache = True


def _normalize_cache_arguments(args, kwargs):
    """
    Return the arguments, with each uuid.UUID changed into its string.

    flask-caching keys on the repr of the arguments. If a function is
    memoized with an ID from an active record (a UUID) and invalidated
    with the same ID from a dict (a string), the two keys are different.
    Then, the invalidation misses the cached entry.
    """
    args = tuple(str(a) if isinstance(a, uuid.UUID) else a for a in args)
    kwargs = {
        key: str(value) if isinstance(value, uuid.UUID) else value
        for key, value in kwargs.items()
    }
    return args, kwargs


def memoize_function(timeout=120):
    """
    Cache the results of the decorated function for timeout seconds. The
    key is the arguments, with UUIDs as strings. With SimpleCache, return
    a deep copy of the cached value (except for ORM instances).
    """

    def decorator(func):
        cached_func = cache.memoize(timeout)(func)

        @wraps(func)
        def wrapper(*args, **kwargs):
            args, kwargs = _normalize_cache_arguments(args, kwargs)
            result = cached_func(*args, **kwargs)
            if not _is_simple_cache:
                return result
            if hasattr(result, "_sa_instance_state"):
                # ORM instances: a deepcopy of their InstanceState is not
                # safe. Callers merge() them into their own session.
                return result
            return copy.deepcopy(result)

        def make_cache_key(f, *args, **kwargs):
            args, kwargs = _normalize_cache_arguments(args, kwargs)
            return cached_func.make_cache_key(f, *args, **kwargs)

        # Copy the flask-caching attributes, so that delete_memoized works.
        # Use the same normalization as the call, so that both sides get
        # the same key.
        wrapper.make_cache_key = make_cache_key
        wrapper.uncached = cached_func.uncached
        wrapper.cache_timeout = cached_func.cache_timeout
        return wrapper

    return decorator


def memoize_function_single_flight(timeout=120):
    """
    Same as memoize_function, with a Redis lock around the rebuild after a
    cache miss. When a hot entry expires, concurrent requests rebuild it
    one time, not all at the same time (anti-stampede). Use it only for
    functions that never return None: the cache cannot tell a None hit
    from a miss.
    """

    def decorator(func):
        cached_func = memoize_function(timeout)(func)

        @wraps(func)
        def wrapper(*args, **kwargs):
            from zou.app.stores.redis_lock import with_lock

            key = cached_func.make_cache_key(
                cached_func.uncached, *args, **kwargs
            )
            if cache.get(key) is not None:
                return cached_func(*args, **kwargs)
            with with_lock(f"single-flight-{key}"):
                return cached_func(*args, **kwargs)

        wrapper.make_cache_key = cached_func.make_cache_key
        wrapper.uncached = cached_func.uncached
        wrapper.cache_timeout = cached_func.cache_timeout
        return wrapper

    return decorator


def clear():
    """
    Delete every cached entry.
    """
    cache.clear()
