"""
Conditional GET support for the JSON endpoints that check permissions.

The copy of the response is in the browser cache of each client. The
ETag must include every input that changes the response: a cheap signal
of data freshness, the identity of the caller and the effective role.
Thus, if the role or the account changes on the same browser, the
revalidation fails. It does not validate a payload made for a different
person.

The responses have the "private, no-cache" policy: the browser keeps the
copy but revalidates it on each request. Thus, the server always decides
with the current authentication before it serves a response.
"""

import hashlib

from flask import current_app, request

from zou.app.utils.flask_utils import dumps_bytes


def build_etag(*parts):
    """
    Hash the given inputs that change the response into an ETag value.
    """
    raw = "|".join(str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_fresh(etag):
    """
    Tell whether the If-None-Match header of the client has the given
    ETag.
    """
    return request.if_none_match.contains(etag)


def not_modified(etag):
    """
    Build an empty 304 response with the given ETag.
    """
    return mark(current_app.response_class(status=304), etag)


def json_response(body, etag):
    """
    Build a JSON response with the given ETag.
    """
    response = current_app.response_class(
        dumps_bytes(body), mimetype="application/json"
    )
    return mark(response, etag)


def mark(response, etag):
    """
    Add the given ETag and the revalidation cache policy to an existing
    response.
    """
    response.set_etag(etag)
    response.cache_control.private = True
    response.cache_control.no_cache = True
    return response
