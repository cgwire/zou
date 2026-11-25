from authlib.integrations.flask_client import OAuth
from flask import current_app

from zou.app import config


def oidc_client_for(app):
    """
    Build the Authlib OAuth registry and register the configured OIDC
    provider from its discovery document. Then, the registered client is
    available as ``oauth.oidc``.
    """
    oauth = OAuth(app)
    oauth.register(
        name="oidc",
        server_metadata_url=config.OIDC_DISCOVERY_URL,
        client_id=config.OIDC_CLIENT_ID,
        client_secret=config.OIDC_CLIENT_SECRET,
        client_kwargs={
            "scope": config.OIDC_SCOPES,
            "code_challenge_method": "S256",
        },
    )
    return oauth


def get_oidc_client():
    """
    Return the registered OIDC client (``oauth.oidc``), which the startup
    stores on the app extensions.
    """
    return current_app.extensions["oidc_client"].oidc


def get_email_from_claims(claims):
    """
    Return the user email from the OIDC claims, with the configured claim
    name (``OIDC_EMAIL_CLAIM``, default: the standard ``email`` claim).
    """
    return claims.get(config.OIDC_EMAIL_CLAIM)


def get_id_token_claims_options(client):
    """
    Return the claims that the ID token must match: the issuer of the
    discovery document and our client ID as audience. By default, Authlib
    checks only the issuer, and it stops this check when it gets options.
    """
    metadata = client.load_server_metadata()
    return {
        "iss": {"essential": True, "values": [metadata["issuer"]]},
        "aud": {"essential": True, "values": [config.OIDC_CLIENT_ID]},
    }


def is_email_verified(claims):
    """
    Tell whether the email is trusted.

    If ``OIDC_REQUIRE_EMAIL_VERIFIED`` is enabled (the default), the
    provider must explicitly assert ``email_verified == true``. If the
    claim is absent, reject the email. This prevents an account takeover
    when Zou links or provisions an account by email with a provider that
    allows unverified addresses.

    If the flag is disabled, reject the email only if the provider
    explicitly states that it is not verified. An absent claim counts as
    verified, for compatibility with providers that do not emit it.
    """
    verified = claims.get("email_verified")
    if config.OIDC_REQUIRE_EMAIL_VERIFIED:
        return verified is True
    return verified is not False


def map_claims(claims):
    """
    Map the OIDC claims to person fields with the configured claim names.
    Return only the fields that have a value, so that empty strings do not
    overwrite the existing values.
    """
    person_info = {}
    first_name = claims.get(config.OIDC_GIVEN_NAME_CLAIM)
    last_name = claims.get(config.OIDC_FAMILY_NAME_CLAIM)
    if first_name:
        person_info["first_name"] = first_name
    if last_name:
        person_info["last_name"] = last_name
    return person_info
