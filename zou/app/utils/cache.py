"""
This module is a wrapper for flask_caching. It configures it and rename
the memoize function. The aim with that cache is to minimize the requests
made on the target database.

When using SimpleCache (in-memory), memoized results are returned by
reference. A deepcopy wrapper is applied so that callers cannot corrupt
the cached objects by mutating them. With Redis the serialization round-
trip already produces a fresh copy, so no extra work is needed.

SQLAlchemy ORM instances are returned as-is without deepcopy: copying
their internal InstanceState is unsafe and produces objects that merge()
rejects as "dirty". Callers holding ORM instances are expected to
session.merge() them, which already creates a session-owned copy and
leaves the cached object untouched.
"""

import copy
import logging
import redis

from functools import wraps

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
        # SimpleCache is per-process: with several workers each one keeps
        # its own copy and delete_memoized() only invalidates the local
        # one, so mutations made by one worker keep being served stale by
        # the others until their TTL expires.
        logger.warning(
            "Cache Redis is unreachable, falling back to in-memory "
            "SimpleCache. With multiple workers, cache invalidation is "
            "BROKEN across processes: stale data may be served. Fix the "
            "Redis connection or set CACHE_TYPE explicitly."
        )
        cache = Cache(config={"CACHE_TYPE": "simple"})
        _is_simple_cache = True


def memoize_function(timeout=120):
    def decorator(func):
        cached_func = cache.memoize(timeout)(func)
        if not _is_simple_cache:
            return cached_func

        @wraps(func)
        def wrapper(*args, **kwargs):
            result = cached_func(*args, **kwargs)
            if hasattr(result, "_sa_instance_state"):
                # ORM instances: returning the detached cached object is
                # safe because callers merge() it into their own session,
                # which produces a fresh copy and never mutates the cache.
                return result
            return copy.deepcopy(result)

        # Copy flask-caching attributes so delete_memoized works
        wrapper.make_cache_key = cached_func.make_cache_key
        wrapper.uncached = cached_func.uncached
        wrapper.cache_timeout = cached_func.cache_timeout
        return wrapper

    return decorator


def memoize_function_single_flight(timeout=120):
    """
    Like memoize_function, plus a Redis lock around cache-miss rebuilds:
    when a hot entry expires, concurrent requests rebuild it once instead
    of all at once (anti-stampede). Reserved for functions that never
    return None, since a None hit is indistinguishable from a miss.
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


def invalidate(*args):
    cache.delete_memoized(*args)


def clear():
    cache.clear()
