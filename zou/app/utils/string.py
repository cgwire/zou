def strtobool(val):
    """
    Convert a string (val) to a boolean value.
    If val is already a boolean return val.
    Else raise ValueError.
    """
    if isinstance(val, bool):
        return val
    if isinstance(val, int):
        return bool(val)
    elif val.lower() in ("y", "yes", "t", "true", "on", "1"):
        return True
    elif val.lower() in ("n", "no", "f", "false", "off", "0"):
        return False
    else:
        raise ValueError
