from fido2.webauthn import (
    PublicKeyCredentialRpEntity,
)
from fido2.server import Fido2Server
from urllib.parse import urlparse

from zou.app import config


def get_fido_server():
    return Fido2Server(
        PublicKeyCredentialRpEntity(
            name="Kitsu", id=urlparse(f"https://{config.DOMAIN_NAME}").hostname
        ),
        verify_origin=(
            None if config.DOMAIN_NAME != "localhost:8080" else lambda a: True
        ),
    )
