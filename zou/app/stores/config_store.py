import sys

import redis

from zou.app import config

USER_LIMIT_KEY = "config:user_limit"
DEFAULT_TIMEZONE_KEY = "config:default_timezone"
DEFAULT_LOCALE_KEY = "config:default_locale"
NOMAD_HOST_KEY = "config:nomad_host"
NOMAD_NORMALIZE_JOB_KEY = "config:nomad_normalize_job"
NOMAD_PLAYLIST_JOB_KEY = "config:nomad_playlist_job"

try:
    config_store = redis.StrictRedis(
        host=config.KEY_VALUE_STORE["host"],
        port=config.KEY_VALUE_STORE["port"],
        db=config.KV_CONFIG_DB_INDEX,
        password=config.KEY_VALUE_STORE["password"],
        decode_responses=True,
    )
    config_store.ping()
except redis.ConnectionError:
    config_store = None
    if "pytest" not in sys.modules:
        print("Cannot access to the required Redis instance")


def _get(key, fallback):
    if config_store is not None:
        try:
            value = config_store.get(key)
            if value is not None:
                return value
        except redis.ConnectionError:
            pass
    return fallback


def _sync(key, env_value):
    if config_store is not None:
        try:
            current = config_store.get(key)
            if current is None or str(current) != str(env_value):
                config_store.set(key, env_value)
        except redis.ConnectionError:
            pass
    return env_value


def get_user_limit():
    return int(_get(USER_LIMIT_KEY, config.USER_LIMIT))


def get_default_timezone():
    return _get(DEFAULT_TIMEZONE_KEY, config.DEFAULT_TIMEZONE)


def get_default_locale():
    return _get(DEFAULT_LOCALE_KEY, config.DEFAULT_LOCALE)


def get_nomad_host():
    return _get(NOMAD_HOST_KEY, config.JOB_QUEUE_NOMAD_HOST)


def get_nomad_normalize_job():
    return _get(NOMAD_NORMALIZE_JOB_KEY, config.JOB_QUEUE_NOMAD_NORMALIZE_JOB)


def get_nomad_playlist_job():
    return _get(NOMAD_PLAYLIST_JOB_KEY, config.JOB_QUEUE_NOMAD_PLAYLIST_JOB)


def sync_config():
    """
    Read config values from environment variables and push them to
    Redis if absent or different. Called at app startup and by the
    ``reload-config`` CLI command.
    Returns a dict of synced values.
    """
    return {
        "user_limit": _sync(USER_LIMIT_KEY, config.USER_LIMIT),
        "default_timezone": _sync(
            DEFAULT_TIMEZONE_KEY, config.DEFAULT_TIMEZONE
        ),
        "default_locale": _sync(DEFAULT_LOCALE_KEY, config.DEFAULT_LOCALE),
        "nomad_host": _sync(NOMAD_HOST_KEY, config.JOB_QUEUE_NOMAD_HOST),
        "nomad_normalize_job": _sync(
            NOMAD_NORMALIZE_JOB_KEY,
            config.JOB_QUEUE_NOMAD_NORMALIZE_JOB,
        ),
        "nomad_playlist_job": _sync(
            NOMAD_PLAYLIST_JOB_KEY,
            config.JOB_QUEUE_NOMAD_PLAYLIST_JOB,
        ),
    }
