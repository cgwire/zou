import sys
import redis

from zou.app import config


try:
    revoked_tokens_store = redis.StrictRedis(
        host=config.KEY_VALUE_STORE["host"],
        port=config.KEY_VALUE_STORE["port"],
        db=config.AUTH_TOKEN_BLACKLIST_KV_INDEX,
        decode_responses=True,
    )
    revoked_tokens_store.ping()
except redis.ConnectionError:
    revoked_tokens_store = None
    if "pytest" not in sys.modules:
        print("Cannot access to the required Redis instance")


def add(key, token, ttl=None):
    """
    Store a token with key as access key.
    """
    return revoked_tokens_store.set(key, token, ex=ttl)


def get(key):
    """
    Retrieve auth token corresponding at given key.
    """
    return revoked_tokens_store.get(key)


def delete(key):
    """
    Remove auth token corresponding at given key.
    """
    return revoked_tokens_store.delete(key)


def keys():
    """
    Get all keys available in the store.
    """
    return [x for x in revoked_tokens_store.keys()]


def clear():
    """
    Clear all auth token stored in the store.
    """
    for key in keys():
        delete(key)


def is_revoked(jti):
    """
    Tell if a stored auth token is revoked or not.
    """
    return get(jti) == "true"
