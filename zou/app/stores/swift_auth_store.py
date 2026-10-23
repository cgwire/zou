"""
Keystone token shared between the processes talking to Swift.

A swiftclient.Connection authenticates against Keystone the first time
it is used. RQ runs every job in a fork of its own, so each job opened
fresh connections and asked Keystone for a token again: one identity
call per stored file, and a job failure whenever Keystone hiccuped. The
storage URL and token are kept here instead, for every process to reuse
until the TTL runs out or Swift refuses the token.

Redis being unavailable is never an error: the connection authenticates
as it would without the cache.
"""

import hashlib
import json
import logging

import redis

from zou.app import config
from zou.app.stores import redis_client

logger = logging.getLogger(__name__)

KEY_PREFIX = "swift:auth:"

# Lazily connected: the pool opens on the first command, not at import.
swift_auth_store = redis_client.get_client(config.KV_CONFIG_DB_INDEX)


def make_key(authurl, user, os_options):
    """
    Build the cache key of an identity: two storages configured with
    different credentials or projects never share a token. Hashed so
    that the user name does not show up in Redis.
    """
    options = os_options or {}
    identity = json.dumps(
        [
            authurl,
            user,
            options.get("tenant_name"),
            options.get("project_name"),
            options.get("region_name"),
        ]
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"{KEY_PREFIX}{digest}"


def get(key):
    """
    Return the cached ``(storage_url, token)`` pair, or ``(None, None)``
    when there is none or Redis cannot be read.
    """
    try:
        value = swift_auth_store.get(key)
    except redis.RedisError:
        logger.warning("Redis unavailable while reading the Swift token")
        return None, None
    if value is None:
        return None, None
    try:
        data = json.loads(value)
        return data["url"], data["token"]
    except (ValueError, KeyError, TypeError):
        return None, None


def add(key, url, token, ttl):
    """
    Share a freshly obtained ``(storage_url, token)`` pair for ``ttl``
    seconds.
    """
    if not url or not token or ttl <= 0:
        return
    try:
        swift_auth_store.set(
            key, json.dumps({"url": url, "token": token}), ex=ttl
        )
    except redis.RedisError:
        logger.warning("Redis unavailable while sharing the Swift token")
