import hashlib
from urllib.parse import urlsplit


def strtobool(val):
    """
    Convert a string (val) to a boolean value.
    If val is already a boolean, return val. If it is an int, return
    bool(val). If it is a string that is not a known boolean word, raise
    ValueError.
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


def mask_secret(value):
    """
    Mask a secret (token, webhook URL), so that a log can show it. Only
    the first and last four characters stay readable. For a URL, only the
    scheme, the host and the port stay readable, whatever the length.
    For another value under 16 characters, nothing stays readable.
    The first eight hex digits of its SHA-256 come after the
    mask. An admin compares the configured value with them through
    `printf %s "$SECRET" | sha256sum | cut -c1-8`. The number of mask
    characters is fixed, so that the length does not leak either.
    """
    if not value:
        return value
    fingerprint = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    url = urlsplit(value)
    if url.scheme and url.hostname:
        # Keep only the host: a netloc can contain credentials.
        port = f":{url.port}" if url.port else ""
        visible = f"{url.scheme}://{url.hostname}{port}/********"
    elif len(value) >= 16:
        visible = f"{value[:4]}********{value[-4:]}"
    else:
        visible = "********"
    return f"{visible} (sha256:{fingerprint})"
