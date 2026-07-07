"""
Lazy, shared Redis client factory.

redis.StrictRedis only opens a connection on the first command, so
building a client is cheap and non-blocking; the stores used to force a
connection at import time with a ping, which slowed startup and made the
whole process fail when Redis was momentarily unreachable.

Clients are memoized per (db index, decode_responses): a given logical
store reuses the same client and its connection pool instead of opening
a new one on every call.
"""

import redis

from zou.app import config

_clients = {}


def get_client(db_index, decode_responses=True):
    """
    Return a memoized Redis client for the given db index. The connection
    is opened lazily on the first command, not here.
    """
    key = (db_index, decode_responses)
    client = _clients.get(key)
    if client is None:
        client = redis.StrictRedis(
            host=config.KEY_VALUE_STORE["host"],
            port=config.KEY_VALUE_STORE["port"],
            db=db_index,
            password=config.KEY_VALUE_STORE["password"],
            decode_responses=decode_responses,
        )
        _clients[key] = client
    return client
