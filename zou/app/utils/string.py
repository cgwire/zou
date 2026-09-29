import hashlib

from urllib.parse import urlsplit


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


def mask_secret(value):
    """
    Mask a secret (token, webhook URL) so it can be written to a log. Only
    the first and last four characters stay readable, the scheme and host
    for a URL, followed by the first eight hex digits of its SHA-256: an
    admin checks the configured value against it with
    `printf %s "$SECRET" | sha256sum | cut -c1-8`. The number of masking
    characters is fixed so the length does not leak either.
    """
    if not value:
        return value
    fingerprint = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    url = urlsplit(value)
    if url.scheme and url.hostname:
        # The host only: a netloc can carry credentials.
        port = f":{url.port}" if url.port else ""
        visible = f"{url.scheme}://{url.hostname}{port}/********"
    elif len(value) >= 16:
        visible = f"{value[:4]}********{value[-4:]}"
    else:
        visible = "********"
    return f"{visible} (sha256:{fingerprint})"
