import base64
import hashlib
import secrets
import time

from unittest import mock

from tests.base import ApiDBTestCase

from zou.app.models.login_log import LoginLog
from zou.app.models.person import Person
from zou.app.services import auth_service, persons_service

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1)"
    " AppleWebKit/537.36 (KHTML, like Gecko)"
    " Chrome/39.0.2171.95 Safari/537.36"
)


def make_challenge(verifier):
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


class AppLoginTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.verifier = secrets.token_urlsafe(48)
        self.challenge = make_challenge(self.verifier)

    def mint(self, code=201, headers=None):
        response = self.app.post(
            "auth/app-login/code",
            json={"code_challenge": self.challenge},
            headers=headers or self.base_headers,
        )
        self.assertEqual(response.status_code, code)
        return response.get_json().get("code")

    def exchange(self, code, verifier=None, headers=None):
        return self.app.post(
            "auth/app-login/token",
            json={"code": code, "code_verifier": verifier or self.verifier},
            headers=headers or {},
        )

    def test_mint_and_exchange(self):
        code = self.mint()
        response = self.exchange(code)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["login"])
        self.assertEqual(data["user"]["id"], str(self.user["id"]))
        self.assertIn("organisation", data)
        self.assertNotIn("password", data["user"])

        response = self.app.get(
            "auth/authenticated",
            headers={"Authorization": f"Bearer {data['access_token']}"},
        )
        self.assertEqual(response.status_code, 200)
        response = self.app.get(
            "auth/refresh-token",
            headers={"Authorization": f"Bearer {data['refresh_token']}"},
        )
        self.assertEqual(response.status_code, 200)

        login_log = (
            LoginLog.query.filter_by(person_id=self.user["id"])
            .order_by(LoginLog.created_at.desc())
            .first()
        )
        self.assertEqual(login_log.origin.code, "script")

    def test_code_is_single_use(self):
        code = self.mint()
        self.assertEqual(self.exchange(code).status_code, 200)
        self.assertEqual(self.exchange(code).status_code, 400)

    def test_code_expires(self):
        with mock.patch.object(auth_service, "APP_LOGIN_CODE_TTL", 1):
            code = self.mint()
        time.sleep(1.5)
        self.assertEqual(self.exchange(code).status_code, 400)

    def test_unknown_code(self):
        response = self.exchange(secrets.token_urlsafe(32))
        self.assertEqual(response.status_code, 400)

    def test_wrong_verifier(self):
        code = self.mint()
        response = self.exchange(code, secrets.token_urlsafe(48))
        self.assertEqual(response.status_code, 400)
        # The failed attempt burnt the code.
        self.assertEqual(self.exchange(code).status_code, 400)

    def test_failures_share_one_message(self):
        code = self.mint()
        wrong_verifier = self.exchange(code, secrets.token_urlsafe(48))
        unknown_code = self.exchange(secrets.token_urlsafe(32))
        self.assertEqual(wrong_verifier.get_json(), unknown_code.get_json())

    def test_malformed_challenge(self):
        for challenge in ["", "short", self.challenge + "A", "+" * 43]:
            response = self.app.post(
                "auth/app-login/code",
                json={"code_challenge": challenge},
                headers=self.base_headers,
            )
            self.assertEqual(response.status_code, 400, challenge)

    def test_inactive_person_at_exchange(self):
        code = self.mint()
        Person.get(self.user["id"]).update({"active": False})
        persons_service.clear_person_cache()
        self.assertEqual(self.exchange(code).status_code, 400)

    def test_bot_cannot_mint(self):
        bot = Person.create(
            first_name="Dev",
            last_name="Agent",
            email="dev.agent@example.com",
            is_bot=True,
        )
        token = persons_service.create_access_token_for_raw_person(bot)
        self.mint(403, {"Authorization": f"Bearer {token}"})

    def test_session_requiring_2fa_setup_cannot_mint(self):
        enforce_2fa = self.flask_app.config["ENFORCE_2FA"]
        self.flask_app.config["ENFORCE_2FA"] = True
        try:
            self.log_in_admin()
            self.mint(403)
        finally:
            self.flask_app.config["ENFORCE_2FA"] = enforce_2fa

    def test_exchange_sets_no_cookie(self):
        code = self.mint()
        response = self.exchange(
            code, headers={"User-Agent": BROWSER_USER_AGENT}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Set-Cookie", response.headers)

    def test_sso_2fa_skip_is_kept(self):
        access_token, _ = auth_service.create_auth_tokens(
            self.user["id"],
            {"identity_type": "person", "skip_2fa_setup": True},
        )
        code = self.mint(headers={"Authorization": f"Bearer {access_token}"})
        refresh_token = self.exchange(code).get_json()["refresh_token"]
        enforce_2fa = self.flask_app.config["ENFORCE_2FA"]
        self.flask_app.config["ENFORCE_2FA"] = True
        try:
            response = self.app.get(
                "auth/refresh-token",
                headers={"Authorization": f"Bearer {refresh_token}"},
            )
            access_token = response.get_json()["access_token"]
            response = self.app.get(
                "data/projects/open",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            self.assertEqual(response.status_code, 200)
        finally:
            self.flask_app.config["ENFORCE_2FA"] = enforce_2fa
