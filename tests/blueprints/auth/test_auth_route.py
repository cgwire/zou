import pyotp
import pytest
import orjson as json

from datetime import timedelta

from tests.base import ApiDBTestCase

from zou.app.utils import auth, date_helpers, fields
from zou.app.models.person import Person
from zou.app.stores import auth_tokens_store
from zou.app.services import auth_service, persons_service

pytestmark = pytest.mark.real_bcrypt


class AuthTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_person()
        self.person.update(
            {
                "password": auth.encrypt_password("secretpassword"),
                "role": "admin",
            }
        )

        self.person_dict = self.person.serialize()
        self.credentials = {
            "email": self.person_dict["email"],
            "password": "secretpassword",
        }

    def tearDown(self):
        self.log_out()
        super().tearDown()

    def get_auth_headers(self, tokens):
        return {"Authorization": f"Bearer {tokens.get('access_token', None)}"}

    def logout(self, tokens):
        headers = self.get_auth_headers(tokens)
        self.app.get("auth/logout", headers=headers)

    def assertIsAuthenticated(self, tokens):
        headers = self.get_auth_headers(tokens)
        response = self.app.get("auth/authenticated", headers=headers)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data.decode("utf-8"))
        self.assertEqual(data["authenticated"], True)

    def assertIsNotAuthenticated(self, tokens, code=401):
        headers = self.get_auth_headers(tokens)
        response = self.app.get("auth/authenticated", headers=headers)
        self.assertEqual(response.status_code, code)

    def test_login(self):
        tokens = self.post("auth/login", self.credentials, 200)

        self.assertIsAuthenticated(tokens)
        self.logout(tokens)

    def test_login_returns_departments(self):
        self.generate_fixture_department()
        persons_service.add_to_department(
            str(self.department.id), str(self.person.id)
        )

        result = self.post("auth/login", self.credentials, 200)
        user = result["user"]
        self.assertIn("departments", user)
        self.assertIn(str(self.department.id), user["departments"])

        # The login payload must carry the same departments as /auth/authenticated
        headers = self.get_auth_headers(result)
        response = self.app.get("auth/authenticated", headers=headers)
        authenticated_user = json.loads(response.data.decode("utf-8"))["user"]
        self.assertEqual(
            sorted(user["departments"]),
            sorted(authenticated_user["departments"]),
        )
        self.logout(result)

    def test_login_args_not_json(self):
        response = self.app.post(
            f"auth/login?email={self.credentials['email']}&password={self.credentials['password']}"
        )
        self.assertEqual(response.status_code, 200)
        tokens = json.loads(response.data.decode("utf-8"))
        self.assertIsAuthenticated(tokens)
        self.logout(tokens)

    def test_unactive_login(self):
        self.person.update({"active": False})
        self.person.save()
        tokens = self.post("auth/login", self.credentials, 401)
        # Flagged rather than spelled out only in the message, so a client
        # does not have to parse English to tell this case apart.
        self.assertTrue(tokens["unactive"])
        self.assertIsNotAuthenticated(tokens, 422)
        self.logout(tokens)

    def test_unactive_login_is_hidden_from_a_wrong_password(self):
        # Reading the account state before the password answered "user is
        # unactive" to anybody holding an address and no credential at all,
        # which tells a registered address from an unknown one.
        self.person.update({"active": False})
        persons_service.clear_person_cache()

        credentials = {
            "email": self.person_dict["email"],
            "password": "wrongpassword",
        }
        result = self.post("auth/login", credentials, 400)
        unknown = self.post(
            "auth/login",
            {"email": "nobody@example.com", "password": "wrongpassword"},
            400,
        )
        self.assertFalse(result["login"])
        self.assertEqual(result, unknown)

    def test_login_with_desktop_login(self):
        self.credentials = {
            "email": self.person_dict["desktop_login"],
            "password": "secretpassword",
        }
        tokens = self.post("auth/login", self.credentials, 200)

        self.assertIsAuthenticated(tokens)
        self.logout(tokens)

    def test_login_wrong_credentials(self):
        result = self.post("auth/login", {}, 400)
        self.assertIsNotAuthenticated(result, 422)

        credentials = {
            "email": self.person_dict["email"],
            "password": "wrongpassword",
        }
        result = self.post("auth/login", credentials, 400)
        self.assertFalse(result["login"])
        self.assertIsNotAuthenticated(result, 422)

    def _fail_login(self, times):
        credentials = {
            "email": self.person_dict["email"],
            "password": "wrongpassword",
        }
        for _ in range(times):
            self.post("auth/login", credentials, 400)

    def _expire_the_lockout_window(self):
        person = Person.get(self.person_dict["id"])
        person.update(
            {
                "last_login_failed": date_helpers.get_utc_now_datetime()
                - timedelta(minutes=2)
            }
        )
        persons_service.clear_person_cache()

    def test_login_lockout_expires_instead_of_rearming(self):
        # Leaving the counter at its ceiling let one wrong password a
        # minute hold the account shut for good, its owner included.
        self._fail_login(5)
        result = self.post("auth/login", self.credentials, 400)
        self.assertTrue(result["too_many_failed_login_attemps"])

        self._expire_the_lockout_window()
        self._fail_login(1)

        # A single wrong password used to lock it straight back.
        self.assertIsAuthenticated(
            self.post("auth/login", self.credentials, 200)
        )

    def test_login_still_locks_after_a_burst(self):
        self._fail_login(5)
        result = self.post("auth/login", self.credentials, 400)
        self.assertTrue(result["too_many_failed_login_attemps"])

        # And a fresh burst locks it again once the window has passed.
        self._expire_the_lockout_window()
        self._fail_login(5)
        result = self.post("auth/login", self.credentials, 400)
        self.assertTrue(result["too_many_failed_login_attemps"])

    def test_unknown_address_costs_a_password_check(self):
        # Answering an unknown address without hashing returned in
        # milliseconds where a real one paid the ~100 ms bcrypt costs, which
        # tells the two apart through responses that are identical. Counted
        # rather than timed, so the check does not depend on the machine.
        calls = []
        original = auth.check_password

        def counting_check_password(password_hash, password):
            calls.append(password_hash)
            return original(password_hash, password)

        auth.check_password = counting_check_password
        try:
            self.post(
                "auth/login",
                {"email": "nobody@example.com", "password": "wrongpassword"},
                400,
            )
        finally:
            auth.check_password = original

        self.assertEqual(len(calls), 1)

    def test_password_less_account_costs_a_password_check(self):
        # A person imported from a CSV has no password at all, and the
        # LDAP sync stores the literal b"default", which is not a hash.
        # Both were refused without hashing, in a millisecond, where an
        # unknown address pays a full bcrypt — one request told them
        # apart. Counted rather than timed, as above.
        for stored_password in [None, b"default"]:
            self.person.update({"password": stored_password})
            persons_service.clear_person_cache()

            calls = []
            original = auth.check_password

            def counting_check_password(password_hash, password):
                calls.append(password_hash)
                return original(password_hash, password)

            auth.check_password = counting_check_password
            try:
                self.post("auth/login", self.credentials, 400)
            finally:
                auth.check_password = original

            # The dummy hash is the one comparison that really runs the
            # KDF: b"default" fails on the salt before doing any work.
            self.assertIn(auth_service._dummy_password_hash, calls)

    def test_wrong_password_does_not_flush_the_person_cache(self):
        # clear_person_cache drops every memoized person lookup for the
        # whole instance, and the JWT loader reads that cache on every
        # authenticated request. Calling it from the failure path let an
        # anonymous caller keep it cold for a few requests a minute.
        calls = []
        original = persons_service.clear_person_cache
        persons_service.clear_person_cache = lambda: calls.append(1)
        try:
            self._fail_login(1)
        finally:
            persons_service.clear_person_cache = original

        self.assertEqual(calls, [])

    def test_logout(self):
        tokens = self.post("auth/login", self.credentials, 200)
        self.assertIsAuthenticated(tokens)
        self.logout(tokens)
        self.assertIsNotAuthenticated(tokens)

    def test_register_route_is_gone(self):
        subscription_data = {
            "email": "alice@doe.com",
            "password": "12345678",
            "password_2": "12345678",
            "first_name": "Alice",
            "last_name": "Doe",
        }
        response = self.app.post(
            "auth/register",
            data=json.dumps(subscription_data),
            headers={"Content-type": "application/json"},
        )
        # With the route removed, nothing matches the path: a plain 404 in
        # production. Under DEBUG the frontend file-serving catch-all
        # (/<fs>/<filename>, GET-only) is registered and captures the path, so
        # the POST is refused with a 405. Either way registration is refused.
        self.assertIn(response.status_code, (404, 405))

    def test_change_password(self):
        credentials = dict(self.credentials)
        tokens = self.post("auth/login", credentials, 200)
        self.assertIsAuthenticated(tokens)

        new_password = {
            "old_password": credentials["password"],
            "password": "87654321",
            "password_2": "87654321",
        }
        credentials = {"email": credentials["email"], "password": "87654321"}

        headers = self.get_auth_headers(tokens)
        headers["Content-type"] = "application/json"
        response = self.app.post(
            "auth/change-password",
            data=json.dumps(new_password),
            headers=headers,
        )
        self.assertEqual(response.status_code, 200)
        self.logout(tokens)

        tokens = self.post("auth/login", credentials, 200)
        self.assertIsAuthenticated(tokens)
        self.logout(tokens)

    def test_logout_revokes_refresh_token(self):
        tokens = self.post("auth/login", self.credentials, 200)
        self.logout(tokens)
        headers = {
            "Authorization": f"Bearer {tokens.get('refresh_token', None)}"
        }
        response = self.app.get("auth/refresh-token", headers=headers)
        self.assertEqual(response.status_code, 401)

    def test_logout_after_refresh_revokes_refresh_token(self):
        tokens = self.post("auth/login", self.credentials, 200)
        refresh_headers = {
            "Authorization": f"Bearer {tokens.get('refresh_token', None)}"
        }
        result = self.app.get("auth/refresh-token", headers=refresh_headers)
        new_tokens = json.loads(result.data.decode("utf-8"))
        self.logout(new_tokens)
        response = self.app.get("auth/refresh-token", headers=refresh_headers)
        self.assertEqual(response.status_code, 401)

    def test_refresh_token(self):
        tokens = self.post("auth/login", self.credentials, 200)
        self.assertIsAuthenticated(tokens)

        headers = {
            "Authorization": f"Bearer {tokens.get('refresh_token', None)}"
        }
        result = self.app.get("auth/refresh-token", headers=headers)
        tokens_string = result.data.decode("utf-8")
        tokens = json.loads(f"{tokens_string}")
        self.assertIsAuthenticated(tokens)

        self.logout(tokens)
        self.assertIsNotAuthenticated(tokens)

    def test_cookies_auth(self):
        user_agent = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1)"
            " AppleWebKit/537.36 (KHTML, like Gecko)"
            " Chrome/39.0.2171.95 Safari/537.36'}"
        )
        headers = {"User-Agent": user_agent}
        headers["Content-type"] = "application/json"

        response = self.app.get("data/persons")
        self.assertEqual(response.status_code, 401)
        response = self.app.post(
            "auth/login",
            data=json.dumps(fields.serialize_value(self.credentials)),
            headers=headers,
        )
        self.assertIn("access_token", response.headers["Set-Cookie"])
        response = self.app.get("data/persons")
        self.assertEqual(response.status_code, 200)
        response = self.app.get("auth/logout", headers=headers)

    def test_reset_password(self):
        email = self.user["email"]
        self.assertIsNotAuthenticated({}, code=422)
        # Unknown and known emails must return the same response so the
        # endpoint cannot be used to enumerate accounts.
        data = {"email": "fake_email@test.com"}
        response = self.post("auth/reset-password", data, 200)
        self.assertTrue(response["success"])
        data = {"email": email}
        response = self.post("auth/reset-password", data, 200)
        self.assertTrue(response["success"])

        token = "token-test"
        new_password = "newpassword"
        auth_tokens_store.add(f"reset-token-{email}", token)
        data = {
            "email": email,
            "token": token,
            "password": new_password,
            "password2": new_password,
        }
        response = self.put("auth/reset-password", data, 200)
        self.assertTrue(response["success"])
        self.post(
            "auth/login", {"email": email, "password": new_password}, 200
        )

    def test_unactive(self):
        self.person.update({"active": False})
        self.post("auth/login", self.credentials, 401)

        self.person.update({"active": True})
        self.person.save()
        persons_service.clear_person_cache()
        tokens = self.post("auth/login", self.credentials, 200)
        headers = self.get_auth_headers(tokens)
        headers["Content-type"] = "application/json"
        self.assertIsAuthenticated(tokens)
        self.app.get("data/persons/", headers=headers)
        self.app.put(
            f"data/persons/{self.person_dict['id']}",
            data=json.dumps({"active": False}),
            headers=headers,
        )
        self.assertIsNotAuthenticated(tokens)

    def test_default_password(self):
        self.person.update(
            {
                "password": auth.encrypt_password("default"),
            }
        )
        self.credentials["password"] = "default"
        response = self.post("auth/login", self.credentials, 400)
        self.assertTrue(response["default_password"])
        data = {
            "email": self.person.email,
            "token": response["token"],
            "password": "complex22pass",
            "password2": "complex22pass",
        }
        response = self.put("auth/reset-password", data, 200)

    def test_get_last_login_logs(self):
        user_artist = self.generate_fixture_user_cg_artist()
        user_manager = self.generate_fixture_user_manager()

        self.log_in(user_artist["email"])
        self.log_in(user_manager["email"])
        self.log_in("john.did@gmail.com")
        login_logs = self.get("/data/events/login-logs/last")
        self.assertEqual(len(login_logs), 4)
        login_logs = self.get("/data/events/login-logs/last?limit=2")
        self.assertEqual(len(login_logs), 2)


class Enforce2FATestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_person()
        self.person.update(
            {
                "password": auth.encrypt_password("secretpassword"),
                "role": "admin",
            }
        )
        self.person_dict = self.person.serialize()
        self.credentials = {
            "email": self.person_dict["email"],
            "password": "secretpassword",
        }
        from zou.app import app

        self.app_instance = app
        self._original_enforce_2fa = app.config["ENFORCE_2FA"]
        self._original_exempt_users = app.config.get("TWO_FA_EXEMPT_USERS", [])
        app.config["ENFORCE_2FA"] = True

    def tearDown(self):
        self.log_out()
        self.app_instance.config["ENFORCE_2FA"] = self._original_enforce_2fa
        self.app_instance.config["TWO_FA_EXEMPT_USERS"] = (
            self._original_exempt_users
        )
        super().tearDown()

    def get_auth_headers(self, tokens):
        return {"Authorization": f"Bearer {tokens.get('access_token', None)}"}

    def test_login_returns_restricted_tokens(self):
        """
        Login with ENFORCE_2FA=True, no 2FA configured returns
        200 with tokens and two_factor_authentication_required.
        """
        response = self.post("auth/login", self.credentials, 200)
        self.assertTrue(response["login"])
        self.assertTrue(response["two_factor_authentication_required"])
        self.assertIn("access_token", response)
        self.assertIn("refresh_token", response)

    def test_restricted_token_blocked_on_non_auth_route(self):
        """
        Restricted token is blocked on non-auth routes with
        403.
        """
        tokens = self.post("auth/login", self.credentials, 200)
        headers = self.get_auth_headers(tokens)
        response = self.app.get("data/persons", headers=headers)
        self.assertEqual(response.status_code, 403)
        data = json.loads(response.data.decode("utf-8"))
        self.assertTrue(data["two_factor_authentication_required"])

    def test_restricted_token_allowed_on_totp(self):
        """
        Restricted token can access /auth/totp for TOTP
        enrollment.
        """
        tokens = self.post("auth/login", self.credentials, 200)
        headers = self.get_auth_headers(tokens)
        headers["Content-type"] = "application/json"
        response = self.app.put("auth/totp", headers=headers)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data.decode("utf-8"))
        self.assertIn("otp_secret", data)

    def test_restricted_token_allowed_on_authenticated(self):
        """
        Restricted token can access /auth/authenticated.
        """
        tokens = self.post("auth/login", self.credentials, 200)
        headers = self.get_auth_headers(tokens)
        response = self.app.get("auth/authenticated", headers=headers)
        self.assertEqual(response.status_code, 200)

    def test_restricted_token_allowed_on_logout(self):
        """
        Restricted token can access /auth/logout.
        """
        tokens = self.post("auth/login", self.credentials, 200)
        headers = self.get_auth_headers(tokens)
        response = self.app.get("auth/logout", headers=headers)
        self.assertEqual(response.status_code, 200)

    def test_restricted_token_blocked_on_change_password(self):
        """
        Restricted token is blocked on /auth/change-password.
        """
        tokens = self.post("auth/login", self.credentials, 200)
        headers = self.get_auth_headers(tokens)
        headers["Content-type"] = "application/json"
        response = self.app.post(
            "auth/change-password",
            data=json.dumps(
                {
                    "old_password": "secretpassword",
                    "password": "newpassword",
                    "password_2": "newpassword",
                }
            ),
            headers=headers,
        )
        self.assertEqual(response.status_code, 403)

    def test_token_unrestricted_after_2fa_setup(self):
        """
        After configuring TOTP, refreshed token is
        unrestricted.
        """
        tokens = self.post("auth/login", self.credentials, 200)
        headers = self.get_auth_headers(tokens)
        headers["Content-type"] = "application/json"

        # Pre-enable TOTP
        response = self.app.put("auth/totp", headers=headers)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data.decode("utf-8"))
        otp_secret = data["otp_secret"]

        # Enable TOTP with a valid code
        totp = pyotp.TOTP(otp_secret)
        response = self.app.post(
            "auth/totp",
            data=json.dumps({"totp": totp.now()}),
            headers=headers,
        )
        self.assertEqual(response.status_code, 200)

        # Clear cached person data
        persons_service.clear_person_cache()

        # Refresh token - should no longer be restricted
        refresh_headers = {
            "Authorization": f"Bearer {tokens.get('refresh_token', None)}"
        }
        response = self.app.get("auth/refresh-token", headers=refresh_headers)
        self.assertEqual(response.status_code, 200)
        new_tokens = json.loads(response.data.decode("utf-8"))

        # New token should access non-auth routes
        new_headers = self.get_auth_headers(new_tokens)
        response = self.app.get("data/persons", headers=new_headers)
        self.assertEqual(response.status_code, 200)

    def test_disable_totp_with_recovery_code(self):
        """
        Disabling TOTP with a recovery code succeeds. Regression: the
        unsafe current-user path exposes recovery codes as raw bytes, which
        used to crash when removing the consumed code.
        """
        tokens = self.post("auth/login", self.credentials, 200)
        headers = self.get_auth_headers(tokens)
        headers["Content-type"] = "application/json"

        response = self.app.put("auth/totp", headers=headers)
        otp_secret = json.loads(response.data.decode("utf-8"))["otp_secret"]
        totp = pyotp.TOTP(otp_secret)
        response = self.app.post(
            "auth/totp",
            data=json.dumps({"totp": totp.now()}),
            headers=headers,
        )
        self.assertEqual(response.status_code, 200)
        recovery_codes = json.loads(response.data.decode("utf-8"))[
            "otp_recovery_codes"
        ]
        persons_service.clear_person_cache()

        response = self.app.delete(
            "auth/totp",
            data=json.dumps({"recovery_code": recovery_codes[0]}),
            headers=headers,
        )
        self.assertEqual(response.status_code, 200)

    def test_exempt_user_gets_unrestricted_tokens(self):
        """
        Users in TWO_FA_EXEMPT_USERS get unrestricted tokens.
        """
        self.app_instance.config["TWO_FA_EXEMPT_USERS"] = [
            self.person_dict["email"]
        ]
        tokens = self.post("auth/login", self.credentials, 200)
        self.assertTrue(tokens["login"])
        self.assertNotIn("two_factor_authentication_required", tokens)
        headers = self.get_auth_headers(tokens)
        response = self.app.get("data/persons", headers=headers)
        self.assertEqual(response.status_code, 200)

    def test_user_with_2fa_configured_can_login(self):
        """
        User with 2FA already configured gets unrestricted
        tokens.
        """
        # Configure TOTP with enforcement disabled
        self.app_instance.config["ENFORCE_2FA"] = False
        tokens = self.post("auth/login", self.credentials, 200)
        headers = self.get_auth_headers(tokens)
        headers["Content-type"] = "application/json"

        response = self.app.put("auth/totp", headers=headers)
        data = json.loads(response.data.decode("utf-8"))
        otp_secret = data["otp_secret"]

        totp = pyotp.TOTP(otp_secret)
        response = self.app.post(
            "auth/totp",
            data=json.dumps({"totp": totp.now()}),
            headers=headers,
        )
        self.assertEqual(response.status_code, 200)
        self.app.get("auth/logout", headers=headers)

        # Re-enable enforcement and login with TOTP
        self.app_instance.config["ENFORCE_2FA"] = True
        persons_service.clear_person_cache()
        login_response = self.post(
            "auth/login",
            {
                "email": self.credentials["email"],
                "password": self.credentials["password"],
                "totp": totp.now(),
            },
            200,
        )
        self.assertTrue(login_response["login"])
        self.assertNotIn(
            "two_factor_authentication_required",
            login_response,
        )

    def test_wrong_password_still_returns_400(self):
        """
        Wrong password returns 400, not 403, even with
        ENFORCE_2FA.
        """
        credentials = {
            "email": self.person_dict["email"],
            "password": "wrongpassword",
        }
        response = self.post("auth/login", credentials, 400)
        self.assertFalse(response["login"])


class EmailOTPTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_person()
        self.person.update(
            {
                "password": auth.encrypt_password("secretpassword"),
                "role": "admin",
            }
        )
        self.person_dict = self.person.serialize()
        self.credentials = {
            "email": self.person_dict["email"],
            "password": "secretpassword",
        }

    def get_auth_headers(self, tokens):
        return {"Authorization": f"Bearer {tokens.get('access_token', None)}"}

    def login(self):
        tokens = self.post("auth/login", self.credentials, 200)
        headers = self.get_auth_headers(tokens)
        headers["Content-type"] = "application/json"
        return tokens, headers

    def get_person(self):
        """
        Reload person from DB to get fresh state.
        """
        return Person.get(self.person_dict["id"])

    def enable_email_otp(self, headers):
        """
        Pre-enable then enable email OTP, return the secret.
        """
        # Pre-enable: generates secret and sends OTP email
        response = self.app.put("auth/email-otp", headers=headers)
        self.assertEqual(response.status_code, 200)

        # Retrieve the secret and OTP counter from store
        person = self.get_person().serialize()
        secret = person["email_otp_secret"]
        count = auth_tokens_store.get(f"email-otp-count-{person['email']}")
        otp = pyotp.HOTP(secret).at(int(count))

        # Enable with the OTP code
        response = self.app.post(
            "auth/email-otp",
            data=json.dumps({"email_otp": otp}),
            headers=headers,
        )
        self.assertEqual(response.status_code, 200)
        return secret

    def test_pre_enable_email_otp(self):
        """
        PUT /auth/email-otp pre-enables email OTP.
        """
        _, headers = self.login()
        response = self.app.put("auth/email-otp", headers=headers)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data.decode("utf-8"))
        self.assertTrue(data["success"])

        # Secret should now be set on the person
        person = self.get_person()
        self.assertIsNotNone(person.email_otp_secret)
        self.assertFalse(person.email_otp_enabled)

    def test_pre_enable_email_otp_already_enabled(self):
        """
        PUT /auth/email-otp returns 400 if already enabled.
        """
        _, headers = self.login()
        self.enable_email_otp(headers)

        response = self.app.put("auth/email-otp", headers=headers)
        self.assertEqual(response.status_code, 400)

    def test_enable_email_otp(self):
        """
        POST /auth/email-otp enables email OTP with valid code.
        """
        _, headers = self.login()
        self.enable_email_otp(headers)

        person = self.get_person()
        self.assertTrue(person.email_otp_enabled)
        self.assertIsNotNone(person.preferred_two_factor_authentication)

    def test_enable_email_otp_wrong_code(self):
        """
        POST /auth/email-otp returns 400 with wrong code.
        """
        _, headers = self.login()

        # Pre-enable
        self.app.put("auth/email-otp", headers=headers)

        # Try to enable with wrong code
        response = self.app.post(
            "auth/email-otp",
            data=json.dumps({"email_otp": "000000"}),
            headers=headers,
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data.decode("utf-8"))
        self.assertTrue(data["wrong_OTP"])

    def test_disable_email_otp(self):
        """
        DELETE /auth/email-otp disables email OTP with valid
        code.
        """
        _, headers = self.login()
        secret = self.enable_email_otp(headers)

        # Manually store a counter and generate OTP for verification
        email = self.person_dict["email"]
        count = 42
        auth_tokens_store.add(f"email-otp-count-{email}", count, ttl=300)
        otp = pyotp.HOTP(secret).at(count)

        response = self.app.delete(
            "auth/email-otp",
            data=json.dumps({"email_otp": otp}),
            headers=headers,
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data.decode("utf-8"))
        self.assertTrue(data["success"])

        # Verify it's disabled
        person = self.get_person()
        self.assertFalse(person.email_otp_enabled)
        self.assertIsNone(person.email_otp_secret)

    def test_disable_email_otp_not_enabled(self):
        """
        DELETE /auth/email-otp returns 400 if not enabled.
        """
        _, headers = self.login()
        response = self.app.delete(
            "auth/email-otp",
            data=json.dumps({"email_otp": "123456"}),
            headers=headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_disable_email_otp_wrong_code(self):
        """
        DELETE /auth/email-otp returns 400 with wrong code.
        """
        _, headers = self.login()
        self.enable_email_otp(headers)

        response = self.app.delete(
            "auth/email-otp",
            data=json.dumps({"email_otp": "000000"}),
            headers=headers,
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data.decode("utf-8"))
        self.assertTrue(data["wrong_OTP"])

    def test_login_with_email_otp(self):
        """
        Login with email OTP after it's enabled.
        """
        tokens, headers = self.login()
        secret = self.enable_email_otp(headers)
        self.app.get("auth/logout", headers=headers)

        # Login without OTP should fail (returns wrong OTP)
        self.post("auth/login", self.credentials, 400)

        # Request OTP via GET
        email = self.credentials["email"]
        response = self.app.get(f"auth/email-otp?email={email}")
        self.assertEqual(response.status_code, 200)

        # Retrieve the counter from store and generate OTP
        count = auth_tokens_store.get(f"email-otp-count-{email}")
        otp = pyotp.HOTP(secret).at(int(count))

        # Login with OTP
        response = self.post(
            "auth/login",
            {
                "email": email,
                "password": self.credentials["password"],
                "email_otp": otp,
            },
            200,
        )
        self.assertTrue(response["login"])

    def test_send_email_otp_not_enabled(self):
        """
        GET /auth/email-otp answers like a sent OTP when the account has
        none enabled, and sends nothing.
        """
        email = self.credentials["email"]
        response = self.app.get(f"auth/email-otp?email={email}")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(auth_tokens_store.get(f"email-otp-count-{email}"))

    def test_send_email_otp_unknown_user(self):
        """
        GET /auth/email-otp answers an unknown address exactly like a known
        one. Answering 404 "User not found." told the two apart in a single
        unauthenticated request.
        """
        known = self.app.get(
            f"auth/email-otp?email={self.credentials['email']}"
        )
        unknown = self.app.get("auth/email-otp?email=unknown@test.com")
        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(unknown.data, known.data)

    def test_send_email_otp_empty_email(self):
        """
        An empty ?email= used to fall through to the desktop login lookup
        and match the first account created without one.
        """
        email = self.credentials["email"]
        self.person.update(
            {
                "desktop_login": "",
                "email_otp_enabled": True,
                "email_otp_secret": pyotp.random_base32(),
            }
        )
        persons_service.clear_person_cache()

        response = self.app.get("auth/email-otp?email=")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(auth_tokens_store.get(f"email-otp-count-{email}"))

    def test_send_email_otp_unactive_user(self):
        """
        A deactivated account gets no OTP email, and is not told apart
        from any other address.
        """
        email = self.credentials["email"]
        self.person.update(
            {
                "active": False,
                "email_otp_enabled": True,
                "email_otp_secret": pyotp.random_base32(),
            }
        )
        persons_service.clear_person_cache()

        response = self.app.get(f"auth/email-otp?email={email}")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(auth_tokens_store.get(f"email-otp-count-{email}"))


class TOTPTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_person()
        self.person.update(
            {
                "password": auth.encrypt_password("secretpassword"),
                "role": "admin",
            }
        )
        self.person_dict = self.person.serialize()
        self.credentials = {
            "email": self.person_dict["email"],
            "password": "secretpassword",
        }

    def get_auth_headers(self, tokens):
        return {"Authorization": f"Bearer {tokens.get('access_token', None)}"}

    def login(self):
        tokens = self.post("auth/login", self.credentials, 200)
        headers = self.get_auth_headers(tokens)
        headers["Content-type"] = "application/json"
        return tokens, headers

    def get_person(self):
        return Person.get(self.person_dict["id"])

    def call_2fa(self, method, path, headers, totp=None, status=200):
        """
        Drive one of the 2FA routes and return its payload. A route that
        takes no code is called with an empty body.
        """
        response = getattr(self.app, method)(
            path,
            data=json.dumps({} if totp is None else {"totp": totp}),
            headers=headers,
        )
        self.assertEqual(response.status_code, status)
        return json.loads(response.data.decode("utf-8"))

    def enable_totp(self, headers):
        """
        Pre-enable then enable TOTP, return the secret.
        """
        otp_secret = self.call_2fa("put", "auth/totp", headers)["otp_secret"]
        self.call_2fa(
            "post", "auth/totp", headers, pyotp.TOTP(otp_secret).now()
        )
        return otp_secret

    def test_pre_enable_totp_already_enabled(self):
        """
        PUT /auth/totp returns 400 if TOTP already enabled.
        """
        _, headers = self.login()
        self.enable_totp(headers)

        data = self.call_2fa("put", "auth/totp", headers, status=400)
        self.assertTrue(data["error"])

    def test_enable_totp_wrong_code(self):
        """
        POST /auth/totp returns 400 with wrong code.
        """
        _, headers = self.login()

        self.call_2fa("put", "auth/totp", headers)
        data = self.call_2fa(
            "post", "auth/totp", headers, "000000", status=400
        )
        self.assertTrue(data["wrong_OTP"])

    def test_enable_totp_already_enabled(self):
        """
        POST /auth/totp returns 400 if TOTP already enabled.
        """
        _, headers = self.login()
        otp_secret = self.enable_totp(headers)

        data = self.call_2fa(
            "post",
            "auth/totp",
            headers,
            pyotp.TOTP(otp_secret).now(),
            status=400,
        )
        self.assertTrue(data["error"])

    def test_disable_totp(self):
        """
        DELETE /auth/totp disables TOTP with valid code.
        """
        _, headers = self.login()
        otp_secret = self.enable_totp(headers)

        data = self.call_2fa(
            "delete", "auth/totp", headers, pyotp.TOTP(otp_secret).now()
        )
        self.assertTrue(data["success"])

        person = self.get_person()
        self.assertFalse(person.totp_enabled)
        self.assertIsNone(person.totp_secret)

    def test_disable_totp_not_enabled(self):
        """
        DELETE /auth/totp returns 400 if TOTP not enabled.
        """
        _, headers = self.login()
        self.call_2fa("delete", "auth/totp", headers, "123456", status=400)

    def test_disable_totp_wrong_code(self):
        """
        DELETE /auth/totp returns 400 with wrong code.
        """
        _, headers = self.login()
        self.enable_totp(headers)

        data = self.call_2fa(
            "delete", "auth/totp", headers, "000000", status=400
        )
        self.assertTrue(data["wrong_OTP"])

    def test_login_with_totp(self):
        """
        Login with TOTP code after enabling.
        """
        _, headers = self.login()
        otp_secret = self.enable_totp(headers)
        self.app.get("auth/logout", headers=headers)

        # Login without TOTP should fail
        self.post("auth/login", self.credentials, 400)

        # Login with TOTP
        totp = pyotp.TOTP(otp_secret)
        response = self.post(
            "auth/login",
            {
                "email": self.credentials["email"],
                "password": self.credentials["password"],
                "totp": totp.now(),
            },
            200,
        )
        self.assertTrue(response["login"])

    def test_login_with_recovery_code(self):
        """
        Login with recovery code after enabling TOTP.
        """
        _, headers = self.login()
        self.enable_totp(headers)

        # Generate a known recovery code
        import flask_bcrypt

        person = self.get_person()
        recovery_code = "testrecovery123"
        hashed = flask_bcrypt.generate_password_hash(recovery_code)
        person.update({"otp_recovery_codes": [hashed]})
        person.save()

        self.app.get("auth/logout", headers=headers)

        # Login with recovery code
        response = self.post(
            "auth/login",
            {
                "email": self.credentials["email"],
                "password": self.credentials["password"],
                "recovery_code": recovery_code,
            },
            200,
        )
        self.assertTrue(response["login"])

    def test_recovery_codes_regeneration(self):
        """
        PUT /auth/recovery-codes regenerates codes with valid
        TOTP.
        """
        _, headers = self.login()
        otp_secret = self.enable_totp(headers)

        data = self.call_2fa(
            "put",
            "auth/recovery-codes",
            headers,
            pyotp.TOTP(otp_secret).now(),
        )
        self.assertIsNotNone(data["otp_recovery_codes"])

    def test_recovery_codes_no_2fa(self):
        """
        PUT /auth/recovery-codes returns 400 without 2FA.
        """
        _, headers = self.login()
        self.call_2fa(
            "put", "auth/recovery-codes", headers, "123456", status=400
        )

    def test_recovery_codes_wrong_otp(self):
        """
        PUT /auth/recovery-codes returns 400 with wrong code.
        """
        _, headers = self.login()
        self.enable_totp(headers)

        data = self.call_2fa(
            "put", "auth/recovery-codes", headers, "000000", status=400
        )
        self.assertTrue(data["wrong_OTP"])


class ChangePasswordErrorsTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_person()
        self.person.update(
            {
                "password": auth.encrypt_password("secretpassword"),
                "role": "admin",
            }
        )
        self.person_dict = self.person.serialize()
        self.credentials = {
            "email": self.person_dict["email"],
            "password": "secretpassword",
        }

    def get_auth_headers(self, tokens):
        return {"Authorization": f"Bearer {tokens.get('access_token', None)}"}

    def login(self):
        tokens = self.post("auth/login", self.credentials, 200)
        headers = self.get_auth_headers(tokens)
        headers["Content-type"] = "application/json"
        return tokens, headers

    def test_a_refused_change_leaves_the_password_alone(self):
        """
        Every way the form can be wrong ends in a 400: the old password has
        to match, the two new ones have to agree, and the new one has to be
        long enough. The status code is half the contract, the other half is
        that the old password still works afterwards.
        """
        _, headers = self.login()
        cases = {
            "the old password is wrong": {
                "old_password": "wrongpassword",
                "password": "newpassword1",
                "password_2": "newpassword1",
            },
            "the two new ones disagree": {
                "old_password": "secretpassword",
                "password": "newpassword1",
                "password_2": "differentpass",
            },
            "the new one is too short": {
                "old_password": "secretpassword",
                "password": "123",
                "password_2": "123",
            },
        }
        for reason, payload in cases.items():
            with self.subTest(reason=reason):
                response = self.app.post(
                    "auth/change-password",
                    data=json.dumps(payload),
                    headers=headers,
                )
                self.assertEqual(response.status_code, 400)
                self.post("auth/login", self.credentials, 200)

    def test_change_password_while_locked_out(self):
        """
        check_auth applies the login lockout here too, and the handler
        used to let TooMuchLoginFailedAttemps out as a 500.
        """
        _, headers = self.login()
        Person.get(self.person_dict["id"]).update(
            {
                "login_failed_attemps": 5,
                "last_login_failed": date_helpers.get_utc_now_datetime(),
            }
        )
        response = self.app.post(
            "auth/change-password",
            data=json.dumps(
                {
                    "old_password": "secretpassword",
                    "password": "newpassword1",
                    "password_2": "newpassword1",
                }
            ),
            headers=headers,
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data.decode("utf-8"))
        self.assertTrue(data["too_many_failed_login_attemps"])
