"""
Authentication of the event stream with the socket.io auth payload.

A browser WebSocket cannot send a header, and a client without a Kitsu
cookie (a desktop application) cannot connect with the handshake request
only. The client sends `{"token": "<access token>"}` in the auth payload of
the connection instead. The checks are the ones of verify_jwt_in_request:
signature, expiry, token type, blocklist and user lookup (account found,
active, 2FA set up when enforced).
"""

import jwt
from flask import g
from flask_jwt_extended import decode_token
from flask_jwt_extended.exceptions import (
    NoAuthorizationError,
    RevokedTokenError,
    WrongTokenError,
)
from flask_jwt_extended.internal_utils import (
    verify_token_not_blocklisted,
    verify_token_type,
)
from flask_jwt_extended.view_decorators import _load_user
from werkzeug.exceptions import Unauthorized

from zou.app.exceptions import (
    InactiveUserException,
    TwoFactorAuthenticationRequiredException,
)

MISSING_TOKEN_MESSAGE = (
    "Missing access token: send the Kitsu cookie, an Authorization header, "
    'or {"token": "<access token>"} in the socket.io auth payload.'
)


def socket_token(auth):
    """
    Return the access token of given socket.io auth payload, or None when
    the payload has none.
    """
    token = auth.get("token") if isinstance(auth, dict) else None
    if isinstance(token, str) and token:
        return token
    return None


def load_socket_token(token):
    """
    Check given access token as verify_jwt_in_request does for a request
    and make it the JWT of the current event: get_jwt_identity() and
    current_user then work in the handler. Raise when the token is not
    valid (any more): see auth_error_message for the cases.
    """
    header = jwt.get_unverified_header(token)
    decoded = decode_token(token)
    verify_token_type(decoded, refresh=False)
    verify_token_not_blocklisted(header, decoded)
    # The attributes that verify_jwt_in_request sets (flask-jwt-extended 4).
    g._jwt_extended_jwt_user = _load_user(header, decoded)
    g._jwt_extended_jwt_header = header
    g._jwt_extended_jwt = decoded
    g._jwt_extended_jwt_location = "socket_auth"


def auth_error_message(error):
    """
    Return the message for the client of given authentication error, one
    per cause, without the internals of the token.
    """
    if isinstance(error, NoAuthorizationError):
        return MISSING_TOKEN_MESSAGE
    if isinstance(error, jwt.ExpiredSignatureError):
        return "Access token expired."
    if isinstance(error, RevokedTokenError):
        return "Access token revoked."
    if isinstance(error, WrongTokenError):
        return "A refresh token was given: send the access token."
    if isinstance(error, InactiveUserException):
        return "Inactive account."
    if isinstance(error, TwoFactorAuthenticationRequiredException):
        return "Two-factor authentication setup is required."
    if isinstance(error, Unauthorized):
        return "Unknown account."
    return "Invalid access token."
