from zou.app import config

REDIS_HOST = config.KEY_VALUE_STORE["host"]
REDIS_PORT = config.KEY_VALUE_STORE["port"]
REDIS_DB = config.KV_JOB_DB_INDEX
REDIS_PASSWORD = config.KEY_VALUE_STORE["password"]
