"""
This module is a wrapper for flask_caching. It configures it and rename
the memoize function. The aim with that cache is to minimize the requests
made on the target database.

When using SimpleCache (in-memory), memoized results are returned by
reference. A deepcopy wrapper is applied so that callers cannot corrupt
the cached objects by mutating them. With Redis the serialization round-
trip already produces a fresh copy, so no extra work is needed.
"""

import copy
import redis

from functools import wraps

from flask_caching import Cache
from zou.app import config

cache = None
_is_simple_cache = False

if config.CACHE_TYPE is not None:
    cache = Cache(config={"CACHE_TYPE": config.CACHE_TYPE})
    _is_simple_cache = config.CACHE_TYPE == "simple"
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
        cache = Cache(config={"CACHE_TYPE": "simple"})
        _is_simple_cache = True


def memoize_function(timeout=120):
    def decorator(func):
        cached_func = cache.memoize(timeout)(func)
        if not _is_simple_cache:
            return cached_func

        @wraps(func)
        def wrapper(*args, **kwargs):
            return copy.deepcopy(cached_func(*args, **kwargs))

        # Copy flask-caching attributes so delete_memoized works
        wrapper.make_cache_key = cached_func.make_cache_key
        wrapper.uncached = cached_func.uncached
        wrapper.cache_timeout = cached_func.cache_timeout
        return wrapper

    return decorator


def invalidate(*args):
    cache.delete_memoized(*args)


def clear():
    cache.clear()
