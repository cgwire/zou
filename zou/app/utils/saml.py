import requests
from saml2 import (
    BINDING_HTTP_POST,
    BINDING_HTTP_REDIRECT,
)
from saml2.client import Saml2Client
from saml2.config import Config as Saml2Config

from zou.app import config


def saml_client_for(metadata_url):
    """
    Download the IdP metadata at the given URL (network call, 30 s
    timeout). Return a Saml2Client configured with it for this service
    provider.
    """
    acs_url = (
        f"{config.DOMAIN_PROTOCOL}://{config.DOMAIN_NAME}/api/auth/saml/sso"
    )

    # The SAML login route also calls saml_client_for at runtime to rebuild
    # the client, so a hung IdP must not block a worker forever.
    rv = requests.get(metadata_url, timeout=30)

    settings = {
        "entityid": f"{config.DOMAIN_PROTOCOL}://{config.DOMAIN_NAME}/api/auth/saml/login",
        "metadata": {"inline": [rv.text]},
        "service": {
            "sp": {
                "endpoints": {
                    "assertion_consumer_service": [
                        (acs_url, BINDING_HTTP_REDIRECT),
                        (acs_url, BINDING_HTTP_POST),
                    ],
                },
                # Do not verify that the incoming requests come from us
                # through the built-in cache of pysaml2 for authn request IDs.
                "allow_unsolicited": True,
                # Do not sign authn requests: signed requests are useful
                # only if you control both the SP and the IdP.
                "authn_requests_signed": False,
                "logout_requests_signed": True,
                "want_assertions_signed": True,
                "want_response_signed": False,
            },
        },
    }
    spConfig = Saml2Config()
    spConfig.load(settings)
    spConfig.allow_unknown_attributes = True
    saml_client = Saml2Client(config=spConfig)
    return saml_client


def get_subject_from_ava(ava):
    """
    Return the stable user ID of the provider from the assertion
    attributes, with the configured attribute name
    (``SAML_SUBJECT_ATTRIBUTE``). If it is absent or ambiguous, return
    None.
    """
    value = ava.get(config.SAML_SUBJECT_ATTRIBUTE)
    if isinstance(value, list) and len(value) == 1:
        value = value[0]
    if isinstance(value, str) and value:
        return value
    return None
