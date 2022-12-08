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
