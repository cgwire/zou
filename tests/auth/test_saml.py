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
from zou.app.services import persons_service


def _fake_authn_response(email, ava):
    response = mock.MagicMock()
    response.get_identity.return_value = ava
    response.get_subject.return_value.text = email
    response.ava = ava
    return response


class SamlRoutesTestCase(ApiDBTestCase):

    def setUp(self):
        super().setUp()
        self._saml_enabled = config.SAML_ENABLED
        config.SAML_ENABLED = True
        self.flask_app.extensions["saml_client"] = mock.MagicMock()

    def tearDown(self):
        config.SAML_ENABLED = self._saml_enabled
        super().tearDown()

    def _post_sso(self, email, ava):
        self.flask_app.extensions[
            "saml_client"
        ].parse_authn_request_response.return_value = _fake_authn_response(
            email, ava
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
