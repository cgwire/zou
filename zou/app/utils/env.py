import os
from zou.app.utils.string import strtobool


def envtobool(key, default=False):
    """
    Convert an environment variable to a boolean value.
    If environment variable can't be converted raise ValueError.
    """
    try:
        return strtobool(os.getenv(key, default))
    except ValueError:
        raise ValueError(
            f"Environment variable {key} cannot be converted to a boolean value."
        )


def env_with_semicolon_to_list(key, default=[]):
    """
    Convert an environment variable to a list.
    Items are separated by semicolon.
    """
    env_value = os.getenv(key, None)
    if env_value is None:
        return default
    else:
        return env_value.split(";")
