import time

from unittest import mock

from authlib.oidc.core import CodeIDToken
from flask_jwt_extended import create_access_token as real_create_access_token

from tests.base import ApiDBTestCase

from zou.app import config
from zou.app.models.person import Person
from zou.app.services import auth_service, persons_service
from zou.app.utils import oidc

ISSUER = "https://idp.example.com"


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

    def validate_id_token(self, audience):
        client = mock.Mock()
        client.load_server_metadata.return_value = {"issuer": ISSUER}
        with mock.patch.object(config, "OIDC_CLIENT_ID", "kitsu"):
            options = oidc.get_id_token_claims_options(client)
        now = int(time.time())
        payload = {
            "iss": ISSUER,
            "sub": "jane",
            "aud": audience,
            "azp": "kitsu",
            "exp": now + 60,
            "iat": now,
        }
        CodeIDToken(
            payload, {}, options=options, params={"client_id": "kitsu"}
        ).validate()

    def test_id_token_for_our_client_is_accepted(self):
        self.validate_id_token("kitsu")

    def test_id_token_for_another_client_is_rejected(self):
        # The error class depends on the Authlib version.
        self.assertRaisesRegex(
            Exception, "aud", self.validate_id_token, "another-app"
        )


class OIDCCallbackTestCase(ApiDBTestCase):
    """Tests for the OIDC callback: provisioning, linking and 2FA gating."""

    def setUp(self):
        super().setUp()
        self._oidc_enabled = config.OIDC_ENABLED
        self._enforce_2fa = config.ENFORCE_2FA
        self._skip_2fa = config.OIDC_SKIP_2FA
        self._require_email_verified = config.OIDC_REQUIRE_EMAIL_VERIFIED
        self._protected_accounts = config.PROTECTED_ACCOUNTS
        config.OIDC_ENABLED = True
        config.ENFORCE_2FA = False
        config.OIDC_SKIP_2FA = False
        config.OIDC_REQUIRE_EMAIL_VERIFIED = True

    def tearDown(self):
        config.OIDC_ENABLED = self._oidc_enabled
        config.ENFORCE_2FA = self._enforce_2fa
        config.OIDC_SKIP_2FA = self._skip_2fa
        config.OIDC_REQUIRE_EMAIL_VERIFIED = self._require_email_verified
        config.PROTECTED_ACCOUNTS = self._protected_accounts
        super().tearDown()

    def mock_client(self, claims, userinfo=None):
        """
        Return a mock OIDC client yielding the given claims as the ID token
        claims. A provider always sends ``iss`` and ``sub``, so they get a
        default value, one subject per email.
        """
        claims = {
            "iss": ISSUER,
            "sub": f"sub-of-{claims.get('email')}",
            **claims,
        }
        client = mock.Mock()
        client.load_server_metadata.return_value = {"issuer": ISSUER}
        client.authorize_access_token.return_value = {"userinfo": claims}
        if userinfo is not None:
            client.userinfo.return_value = userinfo
        return client

    def call_callback(self, claims, userinfo=None):
        client = self.mock_client(claims, userinfo)
        with mock.patch.object(oidc, "get_oidc_client", return_value=client):
            return self.app.get("auth/oidc/callback")

    def sign_in(self, claims):
        """
        Run the callback and return the id of the person who got a session,
        or None when the sign-in was refused.
        """
        with mock.patch.object(
            auth_service,
            "create_auth_tokens",
            wraps=auth_service.create_auth_tokens,
        ) as create_tokens:
            self.call_callback(claims)
        if not create_tokens.called:
            return None
        return create_tokens.call_args.args[0]

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

    def test_returning_user_is_found_by_subject_not_by_email(self):
        claims = {"sub": "jane", "email_verified": True}
        person_id = self.sign_in({**claims, "email": "jane@example.com"})
        self.assertIsNotNone(person_id)
        # The provider renamed her: same subject, new email.
        self.assertEqual(
            self.sign_in({**claims, "email": "jane.doe@example.com"}),
            person_id,
        )
        self.assertRaises(
            Exception,
            persons_service.get_person_by_email,
            "jane.doe@example.com",
        )

    def test_returning_user_needs_no_email_claim(self):
        person_id = self.sign_in(
            {
                "sub": "jane",
                "email": "jane@example.com",
                "email_verified": True,
            }
        )
        self.assertEqual(self.sign_in({"sub": "jane"}), person_id)

    def test_other_subject_with_same_email_is_rejected(self):
        self.generate_fixture_person()
        claims = {
            "email": self.person.email,
            "email_verified": True,
            "given_name": "Mallory",
        }
        self.assertEqual(
            self.sign_in({**claims, "sub": "owner", "given_name": "John"}),
            str(self.person.id),
        )
        response = self.call_callback({**claims, "sub": "mallory"})
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(self.sign_in({**claims, "sub": "mallory"}))
        self.assertEqual(Person.get(self.person.id).first_name, "John")

    def test_protected_account_is_not_linked_by_email(self):
        self.generate_fixture_person()
        config.PROTECTED_ACCOUNTS = [self.person.email]
        claims = {"email": self.person.email, "email_verified": True}
        self.assertEqual(self.call_callback(claims).status_code, 400)
        self.assertIsNone(self.sign_in(claims))
        self.assertIsNone(Person.get(self.person.id).oidc_subject)

    def test_account_is_linked_again_when_the_issuer_changes(self):
        claims = {"email": "jane@example.com", "email_verified": True}
        person_id = self.sign_in({**claims, "sub": "jane"})
        new_identity = {
            **claims,
            "iss": "https://new-idp.example.com",
            "sub": "0042",
        }
        self.assertEqual(self.sign_in(new_identity), person_id)
        self.assertEqual(self.sign_in(new_identity), person_id)

    def test_missing_subject_returns_400(self):
        response = self.call_callback(
            {"sub": "", "email": "nosub@example.com", "email_verified": True}
        )
        self.assertEqual(response.status_code, 400)
        self.assertRaises(
            Exception, persons_service.get_person_by_email, "nosub@example.com"
        )

    def test_userinfo_of_another_subject_is_ignored(self):
        claims = {
            "sub": "jane",
            "email": "jane@example.com",
            "email_verified": True,
        }
        self.call_callback(
            claims, userinfo={"sub": "mallory", "given_name": "Mallory"}
        )
        person = persons_service.get_person_by_email("jane@example.com")
        self.assertEqual(person["first_name"], "")
        self.call_callback(
            claims, userinfo={"sub": "jane", "given_name": "Jane"}
        )
        person = persons_service.get_person_by_email("jane@example.com")
        self.assertEqual(person["first_name"], "Jane")

    def test_id_token_audience_is_checked(self):
        client = self.mock_client(
            {"email": "jane@example.com", "email_verified": True}
        )
        with mock.patch.object(oidc, "get_oidc_client", return_value=client):
            self.app.get("auth/oidc/callback")
        client.authorize_access_token.assert_called_once_with(
            claims_options=oidc.get_id_token_claims_options(client)
        )


class OIDCIdentityFieldsTestCase(ApiDBTestCase):
    """The stored identity is neither readable nor writable by its owner."""

    def setUp(self):
        super().setUp()
        self.generate_fixture_user_cg_artist()
        self.artist_id = str(self.user_cg_artist["id"])

    def link_artist(self):
        persons_service.link_sso_identity(
            self.artist_id, "oidc", ISSUER, "artist"
        )

    def test_identity_is_not_serialized(self):
        self.link_artist()
        person = self.get(f"data/persons/{self.artist_id}")
        for field in (
            "oidc_issuer",
            "oidc_subject",
            "saml_issuer",
            "saml_subject",
        ):
            self.assertNotIn(field, person)

    def test_user_cannot_change_own_identity(self):
        self.link_artist()
        self.log_in_cg_artist()
        self.put(
            f"data/persons/{self.artist_id}",
            {"oidc_subject": "admin", "saml_subject": "admin"},
        )
        person = Person.get(self.artist_id)
        self.assertEqual(person.oidc_subject, "artist")
        self.assertIsNone(person.saml_subject)

    def test_admin_can_unlink_an_account(self):
        self.link_artist()
        self.put(
            f"data/persons/{self.artist_id}",
            {"oidc_issuer": None, "oidc_subject": None},
        )
        self.assertIsNone(Person.get(self.artist_id).oidc_subject)
