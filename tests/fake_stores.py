"""
Point the key-value stores at fakeredis, so that no test needs a Redis
and none can reach a real one.

Building the app syncs the seven config keys, and without a Redis each
command waits for redis-py's connection retries, about seven seconds:
the conftest seeds the stores before create_app. The stores took their
client from the shared factory when zou.app was imported, so the factory
entries and the two module attributes are both replaced; the job queue
db gets a raw client too, the one the status probe counts rq workers on,
sharing the server of the decoded one. The distributed locks open a
client of their own and ping it: the fake runs redis-py's Lock Lua
scripts through fakeredis[lua].

Seeding twice is harmless, and tests/base.py seeds as well: imported
without the conftest (the plugin suites, python -m unittest), it would
otherwise take real clients and flush a real Redis between tests.
"""

import fakeredis


def seed_fake_stores():
    from zou.app import config
    from zou.app.stores import (
        auth_tokens_store,
        config_store,
        redis_client,
        redis_lock,
    )

    job_client = redis_client._clients.get((config.KV_JOB_DB_INDEX, True))
    if isinstance(job_client, fakeredis.FakeStrictRedis):
        return

    for db_index in (
        config.AUTH_TOKEN_BLACKLIST_KV_INDEX,
        config.KV_CONFIG_DB_INDEX,
    ):
        redis_client._clients[(db_index, True)] = fakeredis.FakeStrictRedis(
            decode_responses=True
        )
    job_server = fakeredis.FakeServer()
    for decode_responses in (True, False):
        redis_client._clients[(config.KV_JOB_DB_INDEX, decode_responses)] = (
            fakeredis.FakeStrictRedis(
                server=job_server, decode_responses=decode_responses
            )
        )
    auth_tokens_store.revoked_tokens_store = redis_client.get_client(
        config.AUTH_TOKEN_BLACKLIST_KV_INDEX
    )
    config_store.config_store = redis_client.get_client(
        config.KV_CONFIG_DB_INDEX
    )
    lock_store = fakeredis.FakeStrictRedis(decode_responses=True)
    redis_lock.get_redis_client = lambda: lock_store
