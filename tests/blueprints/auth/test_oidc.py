from unittest import mock

from flask_jwt_extended import create_access_token as real_create_access_token

from tests.base import ApiDBTestCase

from zou.app import config
from zou.app.services import persons_service
from zou.app.utils import oidc


class OIDCClaimMappingTestCase(ApiDBTestCase):
    """Unit tests for the pure claim-mapping helpers."""

    def test_get_email_default_claim(self):
        self.assertEqual(
            oidc.get_email_from_claims({"email": "jane@example.com"}),
            "jane@example.com",
        )

    def test_get_email_overridden_claim(self):
        with mock.patch.object(config, "OIDC_EMAIL_CLAIM", "mail"):
            self.assertEqual(
                oidc.get_email_from_claims({"mail": "jane@corp.com"}),
                "jane@corp.com",
            )

    def test_map_claims_default_claims(self):
        person_info = oidc.map_claims(
            {"given_name": "Jane", "family_name": "Doe"}
        )
        self.assertEqual(
            person_info, {"first_name": "Jane", "last_name": "Doe"}
        )

    def test_map_claims_overridden_claims(self):
        with mock.patch.object(
            config, "OIDC_GIVEN_NAME_CLAIM", "firstName"
        ), mock.patch.object(config, "OIDC_FAMILY_NAME_CLAIM", "surname"):
            person_info = oidc.map_claims(
                {"firstName": "Akira", "surname": "Tanaka"}
            )
        self.assertEqual(
            person_info, {"first_name": "Akira", "last_name": "Tanaka"}
        )

    def test_map_claims_omits_missing_fields(self):
        self.assertEqual(
            oidc.map_claims({"given_name": "Jane"}), {"first_name": "Jane"}
        )
        self.assertEqual(oidc.map_claims({}), {})

    def test_is_email_verified_strict(self):
        with mock.patch.object(config, "OIDC_REQUIRE_EMAIL_VERIFIED", True):
            self.assertFalse(oidc.is_email_verified({}))
            self.assertTrue(oidc.is_email_verified({"email_verified": True}))
            self.assertFalse(oidc.is_email_verified({"email_verified": False}))

    def test_is_email_verified_permissive(self):
        with mock.patch.object(config, "OIDC_REQUIRE_EMAIL_VERIFIED", False):
            self.assertTrue(oidc.is_email_verified({}))
            self.assertTrue(oidc.is_email_verified({"email_verified": True}))
            self.assertFalse(oidc.is_email_verified({"email_verified": False}))


class OIDCCallbackTestCase(ApiDBTestCase):
    """Tests for the OIDC callback: provisioning, linking and 2FA gating."""

    def setUp(self):
        super().setUp()
        self._oidc_enabled = config.OIDC_ENABLED
        self._enforce_2fa = config.ENFORCE_2FA
        self._skip_2fa = config.OIDC_SKIP_2FA
        self._require_email_verified = config.OIDC_REQUIRE_EMAIL_VERIFIED
        config.OIDC_ENABLED = True
        config.ENFORCE_2FA = False
        config.OIDC_SKIP_2FA = False
        config.OIDC_REQUIRE_EMAIL_VERIFIED = True

    def tearDown(self):
        config.OIDC_ENABLED = self._oidc_enabled
        config.ENFORCE_2FA = self._enforce_2fa
        config.OIDC_SKIP_2FA = self._skip_2fa
        config.OIDC_REQUIRE_EMAIL_VERIFIED = self._require_email_verified
        super().tearDown()

    def mock_client(self, claims):
        """Return a mock OIDC client yielding the given claims as userinfo."""
        client = mock.Mock()
        client.authorize_access_token.return_value = {"userinfo": claims}
        return client

    def call_callback(self, claims):
        with mock.patch.object(
            oidc, "get_oidc_client", return_value=self.mock_client(claims)
        ):
            return self.app.get("auth/oidc/callback")

    def test_disabled_returns_400(self):
        config.OIDC_ENABLED = False
        response = self.app.get("auth/oidc/callback")
        self.assertEqual(response.status_code, 400)

    def test_creates_user_on_first_login(self):
        email = "newcomer@example.com"
        self.assertRaises(
            Exception, persons_service.get_person_by_email, email
        )
        response = self.call_callback(
            {
                "email": email,
                "email_verified": True,
                "given_name": "New",
                "family_name": "Comer",
            }
        )
        self.assertEqual(response.status_code, 302)
        person = persons_service.get_person_by_email(email)
        self.assertEqual(person["first_name"], "New")
        self.assertEqual(person["last_name"], "Comer")
        self.assertEqual(person["role"], "user")

    def test_links_existing_user_by_email(self):
        self.generate_fixture_person()
        existing = self.person.serialize()
        response = self.call_callback(
            {
                "email": existing["email"],
                "email_verified": True,
                "given_name": "Updated",
                "family_name": "Name",
            }
        )
        self.assertEqual(response.status_code, 302)
        person = persons_service.get_person_by_email(existing["email"])
        self.assertEqual(person["id"], existing["id"])
        self.assertEqual(person["first_name"], "Updated")

    def test_missing_email_returns_400(self):
        response = self.call_callback(
            {"given_name": "No", "family_name": "Mail"}
        )
        self.assertEqual(response.status_code, 400)

    def test_unverified_email_rejected(self):
        response = self.call_callback(
            {"email": "spoof@example.com", "email_verified": False}
        )
        self.assertEqual(response.status_code, 400)
        self.assertRaises(
            Exception,
            persons_service.get_person_by_email,
            "spoof@example.com",
        )

    def test_absent_email_verified_rejected_when_strict(self):
        response = self.call_callback(
            {
                "email": "noclaim@example.com",
                "given_name": "No",
                "family_name": "Claim",
            }
        )
        self.assertEqual(response.status_code, 400)
        self.assertRaises(
            Exception,
            persons_service.get_person_by_email,
            "noclaim@example.com",
        )

    def test_absent_email_verified_accepted_when_permissive(self):
        config.OIDC_REQUIRE_EMAIL_VERIFIED = False
        response = self.call_callback(
            {
                "email": "permissive@example.com",
                "given_name": "Per",
                "family_name": "Missive",
            }
        )
        self.assertEqual(response.status_code, 302)
        person = persons_service.get_person_by_email("permissive@example.com")
        self.assertEqual(person["first_name"], "Per")

    def test_token_exchange_failure_returns_400(self):
        client = mock.Mock()
        client.authorize_access_token.side_effect = Exception("boom")
        with mock.patch.object(oidc, "get_oidc_client", return_value=client):
            response = self.app.get("auth/oidc/callback")
        self.assertEqual(response.status_code, 400)

    def _capture_claims(self, claims):
        """Run the callback capturing the additional_claims passed to the JWT."""
        with mock.patch(
            "zou.app.services.auth_service.create_access_token",
            wraps=real_create_access_token,
        ) as create_token:
            self.call_callback(claims)
        return create_token.call_args.kwargs["additional_claims"]

    def test_2fa_setup_required_when_enforced(self):
        config.ENFORCE_2FA = True
        config.OIDC_SKIP_2FA = False
        additional_claims = self._capture_claims(
            {
                "email": "needs2fa@example.com",
                "email_verified": True,
                "given_name": "Needs",
                "family_name": "Tfa",
            }
        )
        self.assertTrue(additional_claims.get("requires_2fa_setup"))

    def test_skip_2fa_bypasses_setup_gate(self):
        config.ENFORCE_2FA = True
        config.OIDC_SKIP_2FA = True
        additional_claims = self._capture_claims(
            {
                "email": "skip2fa@example.com",
                "email_verified": True,
                "given_name": "Skip",
                "family_name": "Tfa",
            }
        )
        self.assertNotIn("requires_2fa_setup", additional_claims)
