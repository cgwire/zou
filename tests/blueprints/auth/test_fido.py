"""
FIDO/WebAuthn route tests. The registration options and session state go
through the real fido2 server; only the cryptographic attestation check
(register_complete) is mocked, since it requires a hardware authenticator.
"""

import orjson as json
import pytest

from unittest import mock

from tests.base import ApiDBTestCase

from zou.app.models.person import Person
from zou.app.services import persons_service

# Recovery codes are hashed with bcrypt and their verification is exactly
# what the unregister tests assert.
pytestmark = pytest.mark.real_bcrypt


class FidoRoutesTestCase(ApiDBTestCase):

    def _fake_auth_data(self):
        auth_data = mock.MagicMock()
        auth_data.credential_data.aaguid = b"\x01" * 16
        auth_data.credential_data.credential_id = b"\x02" * 32
        auth_data.credential_data.public_key = {
            1: 2,
            3: -7,
            -1: 1,
            -2: b"\x03" * 32,
            -3: b"\x04" * 32,
        }
        return auth_data

    def _register_device(self, device_name="security-key"):
        self.put("auth/fido", {})
        with mock.patch.object(
            self.flask_app.extensions["fido_server"],
            "register_complete",
            return_value=self._fake_auth_data(),
        ):
            return self.post(
                "auth/fido",
                {
                    "registration_response": {"id": "fake"},
                    "device_name": device_name,
                },
                200,
            )

    def test_get_challenge_unknown_user(self):
        # Answering 404 here and 400 below told a registered address from
        # an unknown one, unauthenticated, in a single request.
        unknown = self.get("auth/fido?email=ghost@nowhere.com", 400)
        known = self.get(f"auth/fido?email={self.user['email']}", 400)
        self.assertEqual(unknown, known)

    def test_get_challenge_fido_not_enabled(self):
        self.get(f"auth/fido?email={self.user['email']}", 400)

    def test_get_challenge_unactive_user(self):
        self._register_device()
        person = Person.get(self.user["id"])
        person.update({"active": False})
        persons_service.clear_person_cache()

        self.get(f"auth/fido?email={self.user['email']}", 400)

    def test_pre_register_returns_webauthn_options(self):
        options = self.put("auth/fido", {})
        self.assertIn("challenge", options)
        self.assertEqual(options["rp"]["name"], "Kitsu")
        self.assertEqual(options["user"]["name"], self.user["email"])

    def test_register_without_preregistration(self):
        self.post(
            "auth/fido",
            {"registration_response": {"id": "fake"}, "device_name": "key"},
            400,
        )

    def test_register_device(self):
        result = self._register_device()
        self.assertGreater(len(result["otp_recovery_codes"]), 0)
        self.assertIn("access_token", result)
        person = Person.get(self.user["id"])
        self.assertTrue(person.fido_enabled)
        self.assertEqual(
            person.fido_credentials[0]["device_name"], "security-key"
        )
        self.assertEqual(
            person.preferred_two_factor_authentication.code, "fido"
        )

    def test_registered_user_gets_a_challenge(self):
        self._register_device()
        challenge = self.get(f"auth/fido?email={self.user['email']}")
        self.assertIn("challenge", challenge)

    def test_unregister_device(self):
        result = self._register_device()
        recovery_code = result["otp_recovery_codes"][0]
        response = self.app.delete(
            "auth/fido",
            data=json.dumps(
                {
                    "device_name": "security-key",
                    "recovery_code": recovery_code,
                }
            ),
            headers=self.post_headers,
        )
        self.assertEqual(response.status_code, 200)
        person = Person.get(self.user["id"])
        self.assertFalse(person.fido_enabled)
        self.assertEqual(person.fido_credentials, [])

    def test_unregister_device_wrong_otp(self):
        self._register_device()
        response = self.app.delete(
            "auth/fido",
            data=json.dumps(
                {"device_name": "security-key", "recovery_code": "wrong"}
            ),
            headers=self.post_headers,
        )
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Person.get(self.user["id"]).fido_enabled)
