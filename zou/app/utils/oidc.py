from authlib.integrations.flask_client import OAuth
from flask import current_app

from zou.app import config


def oidc_client_for(app):
    """
    Build the Authlib OAuth registry and register the configured OIDC
    provider from its discovery document. The registered client is then
    reachable as ``oauth.oidc``.
    """
    oauth = OAuth(app)
    oauth.register(
        name="oidc",
        server_metadata_url=config.OIDC_DISCOVERY_URL,
        client_id=config.OIDC_CLIENT_ID,
        client_secret=config.OIDC_CLIENT_SECRET,
        client_kwargs={"scope": config.OIDC_SCOPES},
    )
    return oauth


def get_oidc_client():
    """
    Return the registered OIDC client (``oauth.oidc``) stored on the app
    extensions at startup.
    """
    return current_app.extensions["oidc_client"].oidc


def get_email_from_claims(claims):
    """
    Resolve the user email from the OIDC claims using the configured claim
    name (``OIDC_EMAIL_CLAIM``, defaults to the standard ``email`` claim).
    """
    return claims.get(config.OIDC_EMAIL_CLAIM)


def is_email_verified(claims):
    """
    Return whether the email can be trusted. We only reject when the
    provider explicitly states the email is not verified; an absent
    ``email_verified`` claim is treated as verified to stay compatible with
    providers that do not emit it.
    """
    return claims.get("email_verified", True) is not False


def map_claims(claims):
    """
    Map OIDC claims to person fields using the configured claim names. Only
    populated fields are returned so existing values are not overwritten with
    empty strings.
    """
    person_info = {}
    first_name = claims.get(config.OIDC_GIVEN_NAME_CLAIM)
    last_name = claims.get(config.OIDC_FAMILY_NAME_CLAIM)
    if first_name:
        person_info["first_name"] = first_name
    if last_name:
        person_info["last_name"] = last_name
    return person_info
