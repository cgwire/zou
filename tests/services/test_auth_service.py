import flask_bcrypt as bcrypt
import pytest

from unittest import mock

from tests.base import ApiDBTestCase

from zou.app.utils import auth

from zou.app import app

from zou.app.stores import auth_tokens_store
from zou.app.services import persons_service, auth_service
from zou.app.services.exception import (
    TwoFactorAuthenticationNotEnabledException,
    UnactiveUserException,
    WrongPasswordException,
    WrongUserException,
)

pytestmark = pytest.mark.real_bcrypt


class AuthTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_person()
        self.person.update(
            {"password": auth.encrypt_password("secretpassword")}
        )

        self.person_dict = self.person.serialize()
        self.credentials = {
            "email": self.person_dict["email"],
            "password": "secretpassword",
        }

    def tearDown(self):
        # Some tests switch the auth strategy; restore the default so the
        # leak does not break login tests run after this file.
        app.config["AUTH_STRATEGY"] = "auth_local_classic"
        super().tearDown()

    def test_encrypt_password(self):
        password = "my secret"
        pass_hash = auth.encrypt_password(password)
        self.assertGreater(len(pass_hash), len(password))
        self.assertNotEqual(pass_hash, password)
        self.assertTrue(bcrypt.check_password_hash(pass_hash, password))

    def test_encrypt_password_long(self):
        """
        Ensure passwords longer than 72 bytes don't raise ValueError
        and can still be verified end-to-end.
        """
        long_password = "password " * 10  # 100 chars
        self.assertGreater(len(long_password), 72)
        pass_hash = auth.encrypt_password(long_password)
        self.assertTrue(auth.check_password(pass_hash, long_password))

    def test_validate_email(self):
        self.assertEqual(
            auth.validate_email("john@gmail.com"), "john@gmail.com"
        )
        self.assertRaises(
            auth.EmailNotValidException, auth.validate_email, "johngmail.com"
        )

    def test_validate_password(self):
        self.assertRaises(
            auth.PasswordTooShortException,
            auth.validate_password,
            "12345",
            "12345",
        )
        self.assertRaises(
            auth.PasswordsNoMatchException,
            auth.validate_password,
            "12345678",
            "12345676",
        )
        self.assertTrue(auth.validate_password("mypassword", "mypassword"))

    def test_no_password_auth_strategy(self):
        app.config["AUTH_STRATEGY"] = "auth_local_no_password"
        person = auth_service.check_auth(app, "john.doe@gmail.com", "")
        self.assertEqual(person["first_name"], "John")

    def test_local_auth_strategy(self):
        app.config["AUTH_STRATEGY"] = "auth_local_classic"
        self.person.update({"password": auth.encrypt_password("mypassword")})
        self.assertRaises(
            WrongPasswordException,
            auth_service.check_auth,
            app,
            "john.doe@gmail.com",
            "mypassword2",
        )
        self.assertRaises(
            WrongUserException,
            auth_service.check_auth,
            app,
            "john.doe@yahoo.com",
            "mypassword2",
        )
        person = auth_service.check_auth(
            app, "john.doe@gmail.com", "mypassword"
        )
        self.assertEqual(person["first_name"], "John")

    def test_unactive_user_is_disclosed_to_the_right_password_only(self):
        app.config["AUTH_STRATEGY"] = "auth_local_classic"
        self.person.update({"active": False})
        persons_service.clear_person_cache()

        self.assertRaises(
            WrongPasswordException,
            auth_service.check_auth,
            app,
            self.person_dict["email"],
            "wrongpassword",
        )
        self.assertRaises(
            UnactiveUserException,
            auth_service.check_auth,
            app,
            self.person_dict["email"],
            "secretpassword",
        )

    def test_unactive_user_is_checked_before_the_second_factor(self):
        # Below the 2FA block, the check would let MissingOTPException go
        # first and hand the enabled 2FA methods of a deactivated account
        # to whoever holds its password.
        app.config["AUTH_STRATEGY"] = "auth_local_classic"
        self.person.update({"active": False, "totp_enabled": True})
        persons_service.clear_person_cache()

        self.assertRaises(
            UnactiveUserException,
            auth_service.check_auth,
            app,
            self.person_dict["email"],
            "secretpassword",
        )

    def test_check_auth_works_on_a_copy(self):
        app.config["AUTH_STRATEGY"] = "auth_local_classic"
        email = self.person_dict["email"]
        person = persons_service.get_person_by_email_desktop_login(email)
        with mock.patch.object(
            persons_service,
            "get_person_by_email_desktop_login",
            return_value=person,
        ):
            result = auth_service.check_auth(app, email, "secretpassword")
        self.assertNotIn("password", result)
        self.assertIn("password", person)

    def test_disable_two_factor_authentication_for_person(self):
        """
        The admin escape hatch: it turns every method off at once, for a user
        who lost the device they were enrolled with.
        """
        self.assertFalse(
            auth_service.person_two_factor_authentication_enabled_raw(
                self.person
            )
        )
        self.assertRaises(
            TwoFactorAuthenticationNotEnabledException,
            auth_service.disable_two_factor_authentication_for_person,
            self.person.id,
        )

        self.person.update(
            {
                "totp_enabled": True,
                "totp_secret": "secret",
                "otp_recovery_codes": [b"code"],
            }
        )
        self.assertTrue(
            auth_service.person_two_factor_authentication_enabled_raw(
                self.person
            )
        )

        auth_service.disable_two_factor_authentication_for_person(
            self.person.id
        )
        self.assertFalse(
            auth_service.person_two_factor_authentication_enabled_raw(
                self.person
            )
        )
        self.assertIsNone(self.person.totp_secret)
        self.assertIsNone(self.person.otp_recovery_codes)

    def test_revoke_tokens(self):
        auth_service.revoke_tokens(
            app, "access-jti", refresh_jti="refresh-jti"
        )
        self.assertTrue(auth_tokens_store.is_revoked("access-jti"))
        self.assertTrue(auth_tokens_store.is_revoked("refresh-jti"))
        self.assertFalse(auth_tokens_store.is_revoked("other-jti"))
