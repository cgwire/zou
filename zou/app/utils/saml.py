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
    Given the name of an IdP, return a configuation.
    The configuration is a hash for use by saml2.config.Config
    """
    acs_url = (
        f"{config.DOMAIN_PROTOCOL}://{config.DOMAIN_NAME}/api/auth/saml/sso"
    )

    rv = requests.get(metadata_url)

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
                # Don't verify that the incoming requests originate from us via
                # the built-in cache for authn request ids in pysaml2
                "allow_unsolicited": True,
                # Don't sign authn requests, since signed requests only make
                # sense in a situation where you control both the SP and IdP
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
