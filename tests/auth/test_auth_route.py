import pyotp
import orjson as json

from tests.base import ApiDBTestCase

from zou.app.utils import auth, fields
from zou.app.models.person import Person
from zou.app.stores import auth_tokens_store
from zou.app.services import persons_service


class AuthTestCase(ApiDBTestCase):
    def setUp(self):
        super(AuthTestCase, self).setUp()

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
        super(AuthTestCase, self).tearDown()

    def get_auth_headers(self, tokens):
        return {
            "Authorization": "Bearer %s" % tokens.get("access_token", None)
        }

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
        self.assertIsNotAuthenticated(tokens, 422)
        self.logout(tokens)

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

    def test_logout(self):
        tokens = self.post("auth/login", self.credentials, 200)
        self.assertIsAuthenticated(tokens)
        self.logout(tokens)
        self.assertIsNotAuthenticated(tokens)

    def test_register(self):
        subscription_data = {
            "email": "alice@doe.com",
            "password": "12345678",
            "password_2": "12345678",
            "first_name": "Alice",
            "last_name": "Doe",
        }
        self.post("auth/register", subscription_data, 201)

        credentials = {
            "email": subscription_data["email"],
            "password": subscription_data["password"],
        }
        tokens = self.post("auth/login", credentials, 200)
        self.assertIsAuthenticated(tokens)
        self.logout(tokens)

    def test_register_bad_email(self):
        credentials = {
            "email": "alicedoecom",
            "password": "12345678",
            "password_2": "12345678",
            "first_name": "Alice",
            "last_name": "Doe",
        }
        self.post("auth/register", credentials, 400)

    def test_register_different_password(self):
        credentials = {
            "email": "alice@doe.com",
            "password": "12345678",
            "password_2": "12345687",
            "first_name": "Alice",
            "last_name": "Doe",
        }
        self.post("auth/register", credentials, 400)

    def test_register_password_too_short(self):
        credentials = {
            "email": "alice@doe.com",
            "password": "123",
            "password_2": "123",
            "first_name": "Alice",
            "last_name": "Doe",
        }
        self.post("auth/register", credentials, 400)

    def test_change_password(self):
        user_data = {
            "email": "alice@doe.com",
            "password": "12345678",
            "password_2": "12345678",
            "first_name": "Alice",
            "last_name": "Doe",
        }
        credentials = {
            "email": "alice@doe.com",
            "password": "12345678",
        }
        self.post("auth/register", user_data, 201)
        tokens = self.post("auth/login", credentials, 200)
        self.assertIsAuthenticated(tokens)

        new_password = {
            "old_password": "12345678",
            "password": "87654321",
            "password_2": "87654321",
        }
        credentials = {"email": "alice@doe.com", "password": "87654321"}

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

    def test_refresh_token(self):
        tokens = self.post("auth/login", self.credentials, 200)
        self.assertIsAuthenticated(tokens)

        headers = {
            "Authorization": "Bearer %s" % tokens.get("refresh_token", None)
        }
        result = self.app.get("auth/refresh-token", headers=headers)
        tokens_string = result.data.decode("utf-8")
        tokens = json.loads("%s" % tokens_string)
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
        self.assertTrue("access_token" in response.headers["Set-Cookie"])
        response = self.app.get("data/persons")
        self.assertEqual(response.status_code, 200)
        response = self.app.get("auth/logout", headers=headers)

    def test_reset_password(self):
        email = self.user["email"]
        self.assertIsNotAuthenticated({}, code=422)
        data = {"email": "fake_email@test.com"}
        self.post("auth/reset-password", data, 400)
        data = {"email": email}
        response = self.post("auth/reset-password", data, 200)
        self.assertTrue(response["success"])

        token = "token-test"
        new_password = "newpassword"
        auth_tokens_store.add("reset-token-%s" % email, token)
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
            "data/persons/%s" % self.person_dict["id"],
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
        return {
            "Authorization": "Bearer %s" % tokens.get("access_token", None)
        }

    def test_login_returns_restricted_tokens(self):
        """Login with ENFORCE_2FA=True, no 2FA configured returns
        200 with tokens and two_factor_authentication_required."""
        response = self.post("auth/login", self.credentials, 200)
        self.assertTrue(response["login"])
        self.assertTrue(response["two_factor_authentication_required"])
        self.assertIn("access_token", response)
        self.assertIn("refresh_token", response)

    def test_restricted_token_blocked_on_non_auth_route(self):
        """Restricted token is blocked on non-auth routes with
        403."""
        tokens = self.post("auth/login", self.credentials, 200)
        headers = self.get_auth_headers(tokens)
        response = self.app.get("data/persons", headers=headers)
        self.assertEqual(response.status_code, 403)
        data = json.loads(response.data.decode("utf-8"))
        self.assertTrue(data["two_factor_authentication_required"])

    def test_restricted_token_allowed_on_totp(self):
        """Restricted token can access /auth/totp for TOTP
        enrollment."""
        tokens = self.post("auth/login", self.credentials, 200)
        headers = self.get_auth_headers(tokens)
        headers["Content-type"] = "application/json"
        response = self.app.put("auth/totp", headers=headers)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data.decode("utf-8"))
        self.assertIn("otp_secret", data)

    def test_restricted_token_allowed_on_authenticated(self):
        """Restricted token can access /auth/authenticated."""
        tokens = self.post("auth/login", self.credentials, 200)
        headers = self.get_auth_headers(tokens)
        response = self.app.get("auth/authenticated", headers=headers)
        self.assertEqual(response.status_code, 200)

    def test_restricted_token_allowed_on_logout(self):
        """Restricted token can access /auth/logout."""
        tokens = self.post("auth/login", self.credentials, 200)
        headers = self.get_auth_headers(tokens)
        response = self.app.get("auth/logout", headers=headers)
        self.assertEqual(response.status_code, 200)

    def test_restricted_token_blocked_on_change_password(self):
        """Restricted token is blocked on /auth/change-password."""
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
        """After configuring TOTP, refreshed token is
        unrestricted."""
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
            "Authorization": "Bearer %s" % tokens.get("refresh_token", None)
        }
        response = self.app.get("auth/refresh-token", headers=refresh_headers)
        self.assertEqual(response.status_code, 200)
        new_tokens = json.loads(response.data.decode("utf-8"))

        # New token should access non-auth routes
        new_headers = self.get_auth_headers(new_tokens)
        response = self.app.get("data/persons", headers=new_headers)
        self.assertEqual(response.status_code, 200)

    def test_exempt_user_gets_unrestricted_tokens(self):
        """Users in TWO_FA_EXEMPT_USERS get unrestricted tokens."""
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
        """User with 2FA already configured gets unrestricted
        tokens."""
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
        """Wrong password returns 400, not 403, even with
        ENFORCE_2FA."""
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
        return {
            "Authorization": "Bearer %s" % tokens.get("access_token", None)
        }

    def login(self):
        tokens = self.post("auth/login", self.credentials, 200)
        headers = self.get_auth_headers(tokens)
        headers["Content-type"] = "application/json"
        return tokens, headers

    def get_person(self):
        """Reload person from DB to get fresh state."""
        return Person.get(self.person_dict["id"])

    def enable_email_otp(self, headers):
        """Pre-enable then enable email OTP, return the secret."""
        # Pre-enable: generates secret and sends OTP email
        response = self.app.put("auth/email-otp", headers=headers)
        self.assertEqual(response.status_code, 200)

        # Retrieve the secret and OTP counter from store
        person = self.get_person().serialize()
        secret = person["email_otp_secret"]
        count = auth_tokens_store.get("email-otp-count-%s" % person["email"])
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
        """PUT /auth/email-otp pre-enables email OTP."""
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
        """PUT /auth/email-otp returns 400 if already enabled."""
        _, headers = self.login()
        self.enable_email_otp(headers)

        response = self.app.put("auth/email-otp", headers=headers)
        self.assertEqual(response.status_code, 400)

    def test_enable_email_otp(self):
        """POST /auth/email-otp enables email OTP with valid code."""
        _, headers = self.login()
        self.enable_email_otp(headers)

        person = self.get_person()
        self.assertTrue(person.email_otp_enabled)
        self.assertIsNotNone(person.preferred_two_factor_authentication)

    def test_enable_email_otp_wrong_code(self):
        """POST /auth/email-otp returns 400 with wrong code."""
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
        """DELETE /auth/email-otp disables email OTP with valid
        code."""
        _, headers = self.login()
        secret = self.enable_email_otp(headers)

        # Manually store a counter and generate OTP for verification
        email = self.person_dict["email"]
        count = 42
        auth_tokens_store.add("email-otp-count-%s" % email, count, ttl=300)
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
        """DELETE /auth/email-otp returns 400 if not enabled."""
        _, headers = self.login()
        response = self.app.delete(
            "auth/email-otp",
            data=json.dumps({"email_otp": "123456"}),
            headers=headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_disable_email_otp_wrong_code(self):
        """DELETE /auth/email-otp returns 400 with wrong code."""
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
        """Login with email OTP after it's enabled."""
        tokens, headers = self.login()
        secret = self.enable_email_otp(headers)
        self.app.get("auth/logout", headers=headers)

        # Login without OTP should fail (returns wrong OTP)
        self.post("auth/login", self.credentials, 400)

        # Request OTP via GET
        email = self.credentials["email"]
        response = self.app.get("auth/email-otp?email=%s" % email)
        self.assertEqual(response.status_code, 200)

        # Retrieve the counter from store and generate OTP
        count = auth_tokens_store.get("email-otp-count-%s" % email)
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
        """GET /auth/email-otp returns 400 if email OTP not enabled."""
        response = self.app.get(
            "auth/email-otp?email=%s" % self.credentials["email"]
        )
        self.assertEqual(response.status_code, 400)

    def test_send_email_otp_unknown_user(self):
        """GET /auth/email-otp returns 404 for unknown email."""
        response = self.app.get("auth/email-otp?email=unknown@test.com")
        self.assertEqual(response.status_code, 404)


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
        return {
            "Authorization": "Bearer %s" % tokens.get("access_token", None)
        }

    def login(self):
        tokens = self.post("auth/login", self.credentials, 200)
        headers = self.get_auth_headers(tokens)
        headers["Content-type"] = "application/json"
        return tokens, headers

    def get_person(self):
        return Person.get(self.person_dict["id"])

    def enable_totp(self, headers):
        """Pre-enable then enable TOTP, return the secret."""
        response = self.app.put("auth/totp", headers=headers)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data.decode("utf-8"))
        otp_secret = data["otp_secret"]

        totp = pyotp.TOTP(otp_secret)
        response = self.app.post(
            "auth/totp",
            data=json.dumps({"totp": totp.now()}),
            headers=headers,
        )
        self.assertEqual(response.status_code, 200)
        return otp_secret

    def test_pre_enable_totp_already_enabled(self):
        """PUT /auth/totp returns 400 if TOTP already enabled."""
        _, headers = self.login()
        self.enable_totp(headers)

        response = self.app.put("auth/totp", headers=headers)
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data.decode("utf-8"))
        self.assertTrue(data["error"])

    def test_enable_totp_wrong_code(self):
        """POST /auth/totp returns 400 with wrong code."""
        _, headers = self.login()

        self.app.put("auth/totp", headers=headers)
        response = self.app.post(
            "auth/totp",
            data=json.dumps({"totp": "000000"}),
            headers=headers,
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data.decode("utf-8"))
        self.assertTrue(data["wrong_OTP"])

    def test_enable_totp_already_enabled(self):
        """POST /auth/totp returns 400 if TOTP already enabled."""
        _, headers = self.login()
        otp_secret = self.enable_totp(headers)

        totp = pyotp.TOTP(otp_secret)
        response = self.app.post(
            "auth/totp",
            data=json.dumps({"totp": totp.now()}),
            headers=headers,
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data.decode("utf-8"))
        self.assertTrue(data["error"])

    def test_disable_totp(self):
        """DELETE /auth/totp disables TOTP with valid code."""
        _, headers = self.login()
        otp_secret = self.enable_totp(headers)

        totp = pyotp.TOTP(otp_secret)
        response = self.app.delete(
            "auth/totp",
            data=json.dumps({"totp": totp.now()}),
            headers=headers,
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data.decode("utf-8"))
        self.assertTrue(data["success"])

        person = self.get_person()
        self.assertFalse(person.totp_enabled)
        self.assertIsNone(person.totp_secret)

    def test_disable_totp_not_enabled(self):
        """DELETE /auth/totp returns 400 if TOTP not enabled."""
        _, headers = self.login()
        response = self.app.delete(
            "auth/totp",
            data=json.dumps({"totp": "123456"}),
            headers=headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_disable_totp_wrong_code(self):
        """DELETE /auth/totp returns 400 with wrong code."""
        _, headers = self.login()
        self.enable_totp(headers)

        response = self.app.delete(
            "auth/totp",
            data=json.dumps({"totp": "000000"}),
            headers=headers,
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data.decode("utf-8"))
        self.assertTrue(data["wrong_OTP"])

    def test_login_with_totp(self):
        """Login with TOTP code after enabling."""
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
        """Login with recovery code after enabling TOTP."""
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
        """PUT /auth/recovery-codes regenerates codes with valid
        TOTP."""
        _, headers = self.login()
        otp_secret = self.enable_totp(headers)

        totp = pyotp.TOTP(otp_secret)
        response = self.app.put(
            "auth/recovery-codes",
            data=json.dumps({"totp": totp.now()}),
            headers=headers,
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data.decode("utf-8"))
        self.assertIn("otp_recovery_codes", data)
        self.assertIsNotNone(data["otp_recovery_codes"])

    def test_recovery_codes_no_2fa(self):
        """PUT /auth/recovery-codes returns 400 without 2FA."""
        _, headers = self.login()
        response = self.app.put(
            "auth/recovery-codes",
            data=json.dumps({"totp": "123456"}),
            headers=headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_recovery_codes_wrong_otp(self):
        """PUT /auth/recovery-codes returns 400 with wrong code."""
        _, headers = self.login()
        self.enable_totp(headers)

        response = self.app.put(
            "auth/recovery-codes",
            data=json.dumps({"totp": "000000"}),
            headers=headers,
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data.decode("utf-8"))
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
        return {
            "Authorization": "Bearer %s" % tokens.get("access_token", None)
        }

    def login(self):
        tokens = self.post("auth/login", self.credentials, 200)
        headers = self.get_auth_headers(tokens)
        headers["Content-type"] = "application/json"
        return tokens, headers

    def test_change_password_wrong_old(self):
        """Change password with wrong old password returns 400."""
        _, headers = self.login()
        response = self.app.post(
            "auth/change-password",
            data=json.dumps(
                {
                    "old_password": "wrongpassword",
                    "password": "newpassword1",
                    "password_2": "newpassword1",
                }
            ),
            headers=headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_change_password_mismatch(self):
        """Change password with mismatched passwords returns 400."""
        _, headers = self.login()
        response = self.app.post(
            "auth/change-password",
            data=json.dumps(
                {
                    "old_password": "secretpassword",
                    "password": "newpassword1",
                    "password_2": "differentpass",
                }
            ),
            headers=headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_change_password_too_short(self):
        """Change password with short password returns 400."""
        _, headers = self.login()
        response = self.app.post(
            "auth/change-password",
            data=json.dumps(
                {
                    "old_password": "secretpassword",
                    "password": "123",
                    "password_2": "123",
                }
            ),
            headers=headers,
        )
