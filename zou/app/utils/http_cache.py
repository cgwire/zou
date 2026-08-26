"""
Conditional GET support for permissioned JSON endpoints.

The response copy lives in each client's browser cache. The ETag must
capture every input that shapes the response: a cheap data freshness
signal, and the caller identity and effective role, so that a role
change or an account switch on the same browser fails revalidation
instead of validating a payload shaped for someone else.

Responses are marked "private, no-cache": the browser keeps the copy
but revalidates on every request, so nothing is ever served without the
server deciding with the current authentication in hand.
"""

import hashlib

from flask import current_app, request

from zou.app.utils.flask_utils import dumps_bytes


def build_etag(*parts):
    """
    Hash the given response-shaping inputs into an ETag value.
    """
    raw = "|".join(str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_fresh(etag):
    """
    Return True when the client's If-None-Match carries given ETag.
    """
    return request.if_none_match.contains(etag)


def not_modified(etag):
    """
    Build an empty 304 response carrying given ETag.
    """
    return mark(current_app.response_class(status=304), etag)


def json_response(body, etag):
    """
    Build a JSON response carrying given ETag.
    """
    response = current_app.response_class(
        dumps_bytes(body), mimetype="application/json"
    )
    return mark(response, etag)


def mark(response, etag):
    """
    Stamp an existing response with given ETag and the revalidation
    cache policy.
    """
    response.set_etag(etag)
    response.cache_control.private = True
    response.cache_control.no_cache = True
    return response
