import datetime

from flask_jwt_extended import create_access_token

from tests.base import ApiDBTestCase

from zou.app.services import auth_service
from zou.app.utils.socket_auth import (
    identity_from_socket_auth,
    load_socket_token,
)


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

    def test_load_socket_token_makes_it_the_jwt_of_the_event(self):
        from flask_jwt_extended import current_user, get_jwt_identity

        with self.flask_app.test_request_context():
            load_socket_token(self.access_token)
            self.assertEqual(get_jwt_identity(), self.user["id"])
            self.assertEqual(str(current_user.id), self.user["id"])

    def test_load_socket_token_refuses_a_token_revoked_after_the_connection(
        self,
    ):
        from flask_jwt_extended import decode_token
        from flask_jwt_extended.exceptions import RevokedTokenError

        jti = decode_token(self.access_token)["jti"]
        auth_service.revoke_tokens(self.flask_app, jti)
        with self.flask_app.test_request_context():
            with self.assertRaises(RevokedTokenError):
                load_socket_token(self.access_token)
