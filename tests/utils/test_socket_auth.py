import datetime

from flask_jwt_extended import create_access_token

from tests.base import ApiDBTestCase

from zou.app.services import auth_service
from zou.app.utils.socket_auth import identity_from_socket_auth


class SocketAuthTestCase(ApiDBTestCase):
    """
    The event stream also accepts the access token in the socket.io auth
    payload: a browser WebSocket cannot send a header.
    """

    def setUp(self):
        super().setUp()
        self.access_token, self.refresh_token = (
            auth_service.create_auth_tokens(
                self.user["id"], {"identity_type": "person"}
            )
        )

    def test_a_valid_access_token_gives_its_identity(self):
        self.assertEqual(
            identity_from_socket_auth({"token": self.access_token}),
            self.user["id"],
        )

    def test_a_missing_token_gives_no_identity(self):
        for auth in [None, {}, {"token": None}, {"token": 42}, "token"]:
            self.assertIsNone(identity_from_socket_auth(auth), auth)

    def test_a_refresh_token_gives_no_identity(self):
        self.assertIsNone(
            identity_from_socket_auth({"token": self.refresh_token})
        )

    def test_an_expired_token_gives_no_identity(self):
        expired = create_access_token(
            identity=self.user["id"],
            additional_claims={"identity_type": "person"},
            expires_delta=datetime.timedelta(seconds=-1),
        )
        self.assertIsNone(identity_from_socket_auth({"token": expired}))

    def test_a_revoked_token_gives_no_identity(self):
        from flask_jwt_extended import decode_token

        jti = decode_token(self.access_token)["jti"]
        auth_service.revoke_tokens(self.flask_app, jti)
        self.assertIsNone(
            identity_from_socket_auth({"token": self.access_token})
        )

    def test_a_bad_signature_gives_no_identity(self):
        header, payload, signature = self.access_token.split(".")
        forged = ".".join([header, payload, signature[::-1]])
        self.assertIsNone(identity_from_socket_auth({"token": forged}))
