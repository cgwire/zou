import logging

from zou.app import config
from zou.app.stores import redis_client

logger = logging.getLogger(__name__)

# Lazily connected: the pool opens on the first command, not at import.
revoked_tokens_store = redis_client.get_client(
    config.AUTH_TOKEN_BLACKLIST_KV_INDEX
)


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
