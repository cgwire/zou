import datetime

from flask_jwt_extended import create_access_token, decode_token
from flask_jwt_extended.exceptions import (
    NoAuthorizationError,
    RevokedTokenError,
    WrongTokenError,
)
from jwt import ExpiredSignatureError
from werkzeug.exceptions import Unauthorized

from tests.base import ApiDBTestCase

from zou.app.exceptions import (
    InactiveUserException,
    TwoFactorAuthenticationRequiredException,
)
from zou.app.services import auth_service, persons_service
from zou.app.utils import fields
from zou.app.utils.socket_auth import (
    MISSING_TOKEN_MESSAGE,
    auth_error_message,
    load_socket_token,
    socket_token,
)


class SocketAuthTestCase(ApiDBTestCase):
    """
    The event stream also accepts the access token in the socket.io auth
    payload: a browser WebSocket cannot send a header. Each refusal has its
    own message for the client.
    """

    def setUp(self):
        super().setUp()
        self.access_token, self.refresh_token = (
            auth_service.create_auth_tokens(
                self.user["id"], {"identity_type": "person"}
            )
        )

    def load(self, token):
        with self.flask_app.test_request_context():
            load_socket_token(token)

    def assertRefused(self, token, error_class, message):
        with self.assertRaises(error_class) as context:
            self.load(token)
        self.assertEqual(auth_error_message(context.exception), message)

    def test_a_valid_access_token_is_the_jwt_of_the_event(self):
        from flask_jwt_extended import current_user, get_jwt_identity

        with self.flask_app.test_request_context():
            load_socket_token(self.access_token)
            self.assertEqual(get_jwt_identity(), self.user["id"])
            self.assertEqual(str(current_user.id), self.user["id"])

    def test_a_payload_without_token_gives_none(self):
        for auth in [None, {}, {"token": None}, {"token": 42}, "token"]:
            self.assertIsNone(socket_token(auth), auth)
        self.assertEqual(
            socket_token({"token": self.access_token}), self.access_token
        )

    def test_a_missing_token_has_its_message(self):
        self.assertEqual(
            auth_error_message(NoAuthorizationError("Missing JWT")),
            MISSING_TOKEN_MESSAGE,
        )

    def test_a_refresh_token_is_refused(self):
        self.assertRefused(
            self.refresh_token,
            WrongTokenError,
            "A refresh token was given: send the access token.",
        )

    def test_an_expired_token_is_refused(self):
        expired = create_access_token(
            identity=self.user["id"],
            additional_claims={"identity_type": "person"},
            expires_delta=datetime.timedelta(seconds=-1),
        )
        self.assertRefused(
            expired, ExpiredSignatureError, "Access token expired."
        )

    def test_a_revoked_token_is_refused(self):
        jti = decode_token(self.access_token)["jti"]
        auth_service.revoke_tokens(self.flask_app, jti)
        self.assertRefused(
            self.access_token, RevokedTokenError, "Access token revoked."
        )

    def test_a_bad_signature_is_refused(self):
        header, payload, signature = self.access_token.split(".")
        forged = ".".join([header, payload, signature[::-1]])
        self.assertRefused(forged, Exception, "Invalid access token.")
        self.assertRefused("not a token", Exception, "Invalid access token.")

    def test_an_inactive_account_is_refused(self):
        person = self.generate_fixture_person()
        token, _ = auth_service.create_auth_tokens(
            str(person.id), {"identity_type": "person"}
        )
        person.update({"active": False})
        persons_service.clear_person_cache()
        self.assertRefused(token, InactiveUserException, "Inactive account.")

    def test_a_token_pending_2fa_setup_is_refused(self):
        token = create_access_token(
            identity=self.user["id"],
            additional_claims={
                "identity_type": "person",
                "requires_2fa_setup": True,
            },
        )
        self.assertRefused(
            token,
            TwoFactorAuthenticationRequiredException,
            "Two-factor authentication setup is required.",
        )

    def test_an_unknown_account_is_refused(self):
        token = create_access_token(
            identity=fields.gen_uuid(),
            additional_claims={"identity_type": "person"},
        )
        self.assertRefused(token, Unauthorized, "Unknown account.")
