import flask_bcrypt as bcrypt
import pytest

from tests.base import ApiDBTestCase

from zou.app.utils import auth

# These assert on the hashing itself, so they need the real bcrypt.
pytestmark = pytest.mark.real_bcrypt


class AuthUtilsTestCase(ApiDBTestCase):
    """
    The password and email primitives the authentication is built on.
    """

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

    def test_check_password_of_a_wrong_password(self):
        pass_hash = auth.encrypt_password("my secret")
        self.assertFalse(auth.check_password(pass_hash, "my other secret"))

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
