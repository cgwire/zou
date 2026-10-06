"""
SAML SSO route tests. The pysaml2 client (network + XML signature checks)
is mocked: only Zou's own behaviour is exercised, that is the enabled
gate, user provisioning from the assertion, updates on later logins and
the auth cookies.
"""

from unittest import mock

from tests.base import ApiDBTestCase

from zou.app import config
from zou.app.models.person import Person
from zou.app.services import auth_service, persons_service

IDP = "https://idp.example.com/saml"
JANE = {"first_name": ["Jane"], "last_name": ["Doe"]}


def _fake_authn_response(email, ava, issuer=IDP):
    response = mock.MagicMock()
    response.get_identity.return_value = ava
    response.get_subject.return_value.text = email
    response.issuer.return_value = issuer
    response.ava = ava
    return response


class SamlRoutesTestCase(ApiDBTestCase):

    def setUp(self):
        super().setUp()
        self._saml_enabled = config.SAML_ENABLED
        self._subject_attribute = config.SAML_SUBJECT_ATTRIBUTE
        self._protected_accounts = config.PROTECTED_ACCOUNTS
        config.SAML_ENABLED = True
        self.flask_app.extensions["saml_client"] = mock.MagicMock()

    def tearDown(self):
        config.SAML_ENABLED = self._saml_enabled
        config.SAML_SUBJECT_ATTRIBUTE = self._subject_attribute
        config.PROTECTED_ACCOUNTS = self._protected_accounts
        super().tearDown()

    def _post_sso(self, email, ava, issuer=IDP):
        self.flask_app.extensions[
            "saml_client"
        ].parse_authn_request_response.return_value = _fake_authn_response(
            email, ava, issuer
        )
        return self.app.post(
            "auth/saml/sso",
            data={"SAMLResponse": "fake"},
            headers=self.base_headers,
        )

    def test_sso_disabled_returns_400(self):
        config.SAML_ENABLED = False
        response = self.app.post(
            "auth/saml/sso",
            data={"SAMLResponse": "fake"},
            headers=self.base_headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_login_redirect_disabled_returns_400(self):
        config.SAML_ENABLED = False
        response = self.app.get("auth/saml/login", headers=self.base_headers)
        self.assertEqual(response.status_code, 400)

    def test_login_redirect_points_to_idp(self):
        self.flask_app.extensions[
            "saml_client"
        ].prepare_for_authenticate.return_value = (
            None,
            {"headers": [("Location", "https://idp.example.com/sso")]},
        )
        response = self.app.get("auth/saml/login", headers=self.base_headers)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers["Location"], "https://idp.example.com/sso"
        )

    def test_sso_provisions_new_user(self):
        response = self._post_sso(
            "newcomer@example.com",
            {
                "first_name": ["Jane"],
                "last_name": ["Doe"],
                "country": ["fr"],
            },
        )
        self.assertEqual(response.status_code, 302)
        person = persons_service.get_person_by_email("newcomer@example.com")
        self.assertEqual(person["first_name"], "Jane")
        self.assertEqual(person["last_name"], "Doe")
        # country is normalized to its canonical uppercase form.
        self.assertEqual(person["country"], "FR")
        self.assertIn("access_token_cookie", response.headers["Set-Cookie"])

    def test_sso_updates_existing_user(self):
        self.generate_fixture_person(
            first_name="Old", last_name="Name", email="known@example.com"
        )
        self._post_sso(
            "known@example.com",
            {"first_name": ["New"], "last_name": ["Name"]},
        )
        person = persons_service.get_person_by_email("known@example.com")
        self.assertEqual(person["first_name"], "New")

    def test_sso_drops_malformed_country(self):
        self._post_sso(
            "badcountry@example.com",
            {
                "first_name": ["Ada"],
                "last_name": ["Lovelace"],
                "country": ["Wonderland"],
            },
        )
        person = Person.get_by(email="badcountry@example.com")
        self.assertIsNotNone(person)
        self.assertIn(person.country, (None, ""))

    def _sign_in(self, email, ava, issuer=IDP):
        """
        Post the assertion and return the id of the person who got a
        session, or None when the sign-in was refused.
        """
        with mock.patch.object(
            auth_service,
            "create_auth_tokens",
            wraps=auth_service.create_auth_tokens,
        ) as create_tokens:
            self._post_sso(email, ava, issuer)
        if not create_tokens.called:
            return None
        return create_tokens.call_args.args[0]

    def test_returning_user_is_found_by_subject_not_by_email(self):
        config.SAML_SUBJECT_ATTRIBUTE = "uid"
        person_id = self._sign_in(
            "jane@example.com", {**JANE, "uid": ["jane"]}
        )
        self.assertIsNotNone(person_id)
        # The provider renamed her: same subject, new email.
        self.assertEqual(
            self._sign_in("jane.doe@example.com", {**JANE, "uid": ["jane"]}),
            person_id,
        )
        self.assertIsNone(Person.get_by(email="jane.doe@example.com"))

    def test_other_subject_with_same_email_is_rejected(self):
        config.SAML_SUBJECT_ATTRIBUTE = "uid"
        self.generate_fixture_person(
            first_name="John", email="known@example.com"
        )
        self.assertEqual(
            self._sign_in(
                "known@example.com", {"uid": ["owner"], "first_name": ["John"]}
            ),
            str(self.person.id),
        )
        ava = {"uid": ["mallory"], "first_name": ["Mallory"]}
        response = self._post_sso("known@example.com", ava)
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(self._sign_in("known@example.com", ava))
        self.assertEqual(Person.get(self.person.id).first_name, "John")

    def test_protected_account_is_not_linked_by_email(self):
        config.SAML_SUBJECT_ATTRIBUTE = "uid"
        self.generate_fixture_person(email="known@example.com")
        config.PROTECTED_ACCOUNTS = ["known@example.com"]
        response = self._post_sso("known@example.com", {"uid": ["mallory"]})
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(Person.get(self.person.id).saml_subject)

    def test_missing_subject_attribute_is_rejected(self):
        config.SAML_SUBJECT_ATTRIBUTE = "uid"
        response = self._post_sso("nouid@example.com", JANE)
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(Person.get_by(email="nouid@example.com"))

    def test_account_is_linked_again_when_the_provider_changes(self):
        config.SAML_SUBJECT_ATTRIBUTE = "uid"
        person_id = self._sign_in(
            "jane@example.com", {**JANE, "uid": ["jane"]}
        )
        new_idp = "https://new-idp.example.com/saml"
        self.assertEqual(
            self._sign_in(
                "jane@example.com", {**JANE, "uid": ["0042"]}, new_idp
            ),
            person_id,
        )

    def test_saml_and_oidc_identities_are_independent(self):
        config.SAML_SUBJECT_ATTRIBUTE = "uid"
        person_id = self._sign_in(
            "jane@example.com", {**JANE, "uid": ["jane"]}
        )
        persons_service.link_sso_identity(
            person_id, "oidc", "https://idp.example.com", "jane-oidc"
        )
        person = Person.get(person_id)
        self.assertEqual(person.saml_subject, "jane")
        self.assertEqual(person.oidc_subject, "jane-oidc")
        self.assertIsNone(
            self._sign_in("jane@example.com", {**JANE, "uid": ["eve"]})
        )

    def test_without_subject_attribute_accounts_are_matched_by_email(self):
        person_id = self._sign_in(
            "jane@example.com", {**JANE, "uid": ["jane"]}
        )
        self.assertEqual(
            self._sign_in("jane@example.com", {**JANE, "uid": ["other"]}),
            person_id,
        )
        self.assertIsNone(Person.get(person_id).saml_subject)
