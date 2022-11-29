def strtobool(val):
    if isinstance(val, bool):
        return val
    elif val.lower() in ("y", "yes", "t", "true", "on", "1"):
        return True
    elif val.lower() in ("n", "no", "f", "false", "off", "0"):
        return False
    else:
        raise ValueError
