from zou.app import config


def get_redis_url(db_index):
    redis_host = config.KEY_VALUE_STORE["host"]
    redis_port = config.KEY_VALUE_STORE["port"]
    if config.KEY_VALUE_STORE["password"]:
        redis_password = f":{config.KEY_VALUE_STORE['password']}@"
    else:
        redis_password = ""
    return f"redis://{redis_password}{redis_host}:{redis_port}/{db_index}"
