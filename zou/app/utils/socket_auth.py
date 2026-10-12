"""
Authentication of the event stream with the socket.io auth payload.

A browser WebSocket cannot send a header, and a client without a Kitsu
cookie (a desktop application) cannot connect with the handshake request
only. The client sends `{"token": "<access token>"}` in the auth payload of
the connection instead. The checks are the ones of verify_jwt_in_request:
signature, expiry, token type and blocklist.
"""

import jwt
from flask import g
from flask_jwt_extended import decode_token
from flask_jwt_extended.config import config as jwt_config
from flask_jwt_extended.exceptions import JWTExtendedException
from flask_jwt_extended.internal_utils import (
    verify_token_not_blocklisted,
    verify_token_type,
)
from flask_jwt_extended.view_decorators import _load_user


def _verified(token):
    """
    Return the header and the claims of given access token, after the
    checks of verify_jwt_in_request. Raise when the token is not valid.
    """
    header = jwt.get_unverified_header(token)
    decoded = decode_token(token)
    verify_token_type(decoded, refresh=False)
    verify_token_not_blocklisted(header, decoded)
    return header, decoded


def identity_from_socket_auth(auth):
    """
    Return the identity of the access token of given socket.io auth payload,
    or None when the payload has no valid access token.
    """
    token = auth.get("token") if isinstance(auth, dict) else None
    if not isinstance(token, str) or not token:
        return None
    try:
        _, decoded = _verified(token)
    except (JWTExtendedException, jwt.PyJWTError):
        return None
    return decoded.get(jwt_config.identity_claim_key)


def load_socket_token(token):
    """
    Check given access token again and make it the JWT of the current event,
    as verify_jwt_in_request does for a request: get_jwt_identity() and
    current_user then work in the handler. Raise when the token is not
    valid any more (expired or revoked during the connection).
    """
    header, decoded = _verified(token)
    # The attributes that verify_jwt_in_request sets (flask-jwt-extended 4).
    g._jwt_extended_jwt_user = _load_user(header, decoded)
    g._jwt_extended_jwt_header = header
    g._jwt_extended_jwt = decoded
    g._jwt_extended_jwt_location = "socket_auth"
