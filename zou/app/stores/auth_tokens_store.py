import json
import logging
import math
import time

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


def add_to_token_set(key, token, ttl, size):
    """
    Add given token to the token set stored at given key, valid for ttl
    seconds. Each token of the set expires on its own. The set holds size
    tokens at most: the ones that expire first make room for the new one.

    The set is stored as a JSON string, so the commands that read every key
    of the store as a string still work. Reading and writing it run in one
    transaction: Redis refuses the write when another client changes the key
    in between, and the transaction starts over.
    """

    def add(pipe):
        now = time.time()
        tokens = _read_token_set(pipe, key, now)
        others = sorted(tokens.items(), key=lambda item: item[1])
        kept = dict(others[max(len(others) - size + 1, 0) :])
        kept[token] = now + ttl
        pipe.multi()
        _write_token_set(pipe, key, kept, now)

    revoked_tokens_store.transaction(add, key)


def get_token_set(key):
    """
    Return the valid tokens of the token set stored at given key, with the
    seconds each one has left.
    """
    now = time.time()
    tokens = _read_token_set(revoked_tokens_store, key, now)
    return {token: expiry - now for token, expiry in tokens.items()}


def remove_from_token_set(key, token):
    """
    Remove given token from the token set stored at given key. Return True
    if the token was valid: of two calls for the same token, only one does.
    """

    def remove(pipe):
        now = time.time()
        tokens = _read_token_set(pipe, key, now)
        found = tokens.pop(token, None) is not None
        pipe.multi()
        if found:
            _write_token_set(pipe, key, tokens, now)
        return found

    return revoked_tokens_store.transaction(
        remove, key, value_from_callable=True
    )


def _read_token_set(client, key, now):
    value = client.get(key)
    tokens = json.loads(value) if value else {}
    return {token: expiry for token, expiry in tokens.items() if expiry > now}


def _write_token_set(pipe, key, tokens, now):
    if tokens:
        ttl = math.ceil(max(tokens.values()) - now)
        pipe.set(key, json.dumps(tokens), ex=ttl)
    else:
        pipe.delete(key)


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
