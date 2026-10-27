import datetime
from unittest import mock

import pytest

from tests.services.cases import AuthTestCase
from zou.app import app, db
from zou.app.exceptions import (
    InactiveUserException,
    MissingOTPException,
    NoAuthStrategyConfigured,
    TooManyLoginFailedAttempts,
    TwoFactorAuthenticationNotEnabledException,
    UserCantConnectDueToNoFallback,
    WrongPasswordException,
    WrongUserException,
)
from zou.app.models.person import SENSITIVE_FIELDS, Person
from zou.app.services import auth_service, persons_service
from zou.app.stores import auth_tokens_store
from zou.app.utils import auth, date_helpers

# The whole point of these is what a password check accepts and refuses.
pytestmark = pytest.mark.real_bcrypt


class CheckAuthTestCase(AuthTestCase):
    """
    What a login accepts and refuses, and what it hands back.
    """

    def test_local_auth_strategy(self):
        app.config["AUTH_STRATEGY"] = "auth_local_classic"
        self.assertEqual(self.authenticate()["first_name"], "John")

    def test_local_auth_strategy_with_a_wrong_password(self):
        app.config["AUTH_STRATEGY"] = "auth_local_classic"
        self.assertRaises(WrongPasswordException, self.authenticate, "wrong")

    def test_local_auth_strategy_on_a_person_without_a_password(self):
        """
        An empty hash must not read as a match, whatever is sent.
        """
        app.config["AUTH_STRATEGY"] = "auth_local_classic"
        self.person.update({"password": None})
        self.assertRaises(WrongPasswordException, self.authenticate, "")

    def test_local_auth_strategy_on_an_unreadable_hash(self):
        """
        A row carrying something that is not a bcrypt hash makes the
        comparison raise. It is a wrong password, not a 500.
        """
        app.config["AUTH_STRATEGY"] = "auth_local_classic"
        self.person.update({"password": b"not-a-hash"})
        persons_service.clear_person_cache()
        self.assertRaises(WrongPasswordException, self.authenticate)

    def test_an_unknown_address(self):
        self.assertRaises(
            WrongUserException,
            auth_service.check_auth,
            app,
            "nobody@example.com",
            "secretpassword",
        )

    def test_no_address_at_all(self):
        self.assertRaises(
            WrongUserException, auth_service.check_auth, app, "", "password"
        )

    def test_an_unknown_address_costs_a_password_check(self):
        """
        Answering an unknown address without paying the bcrypt round the
        known ones pay tells an attacker which addresses are registered.
        """
        with mock.patch.object(
            auth_service, "_spend_password_check_time"
        ) as spend:
            self.assertRaises(
                WrongUserException,
                auth_service.check_auth,
                app,
                "nobody@example.com",
                "secretpassword",
            )
        spend.assert_called_once_with("secretpassword")

    def test_an_inactive_person(self):
        self.person.update({"active": False})
        persons_service.clear_person_cache()
        self.assertRaises(InactiveUserException, self.authenticate)

    def test_no_password_auth_strategy(self):
        app.config["AUTH_STRATEGY"] = "auth_local_no_password"
        self.assertEqual(self.authenticate("")["first_name"], "John")

    def test_no_strategy_configured(self):
        app.config["AUTH_STRATEGY"] = "auth_nothing_at_all"
        self.assertRaises(NoAuthStrategyConfigured, self.authenticate)

    def test_check_auth_hands_back_no_secret(self):
        """
        The dict this returns is the one the login route puts in its
        response body, and it was read with the unsafe serialization to
        reach the secrets it checks against.
        """
        app.config["AUTH_STRATEGY"] = "auth_local_classic"
        self.person.update(
            {
                "jti": "a-token-id",
                "totp_secret": "a-secret",
                "email_otp_secret": "another-secret",
                "otp_recovery_codes": [b"a-code"],
            }
        )
        persons_service.clear_person_cache()

        result = self.authenticate()

        self.assertEqual(
            [field for field in SENSITIVE_FIELDS if field in result], []
        )
        self.assertEqual(result["id"], self.person_id)

    def test_unactive_user_is_disclosed_to_the_right_password_only(self):
        app.config["AUTH_STRATEGY"] = "auth_local_classic"
        self.person.update({"active": False})
        persons_service.clear_person_cache()

        self.assertRaises(WrongPasswordException, self.authenticate, "wrong")
        self.assertRaises(InactiveUserException, self.authenticate)

    def test_unactive_user_is_checked_before_the_second_factor(self):
        # Below the 2FA block, the check would let MissingOTPException go
        # first and hand the enabled 2FA methods of a deactivated account
        # to whoever holds its password.
        app.config["AUTH_STRATEGY"] = "auth_local_classic"
        self.person.update({"active": False, "totp_enabled": True})
        persons_service.clear_person_cache()

        self.assertRaises(InactiveUserException, self.authenticate)

    def test_check_auth_works_on_a_copy(self):
        """
        The person may come straight from the memoize cache, which the
        stripping must not reach into.
        """
        app.config["AUTH_STRATEGY"] = "auth_local_classic"
        person = persons_service.get_person_by_email_desktop_login(self.email)
        with mock.patch.object(
            persons_service,
            "get_person_by_email_desktop_login",
            return_value=person,
        ):
            result = self.authenticate()
        self.assertNotIn("password", result)
        self.assertIn("password", person)


class LdapStrategyTestCase(AuthTestCase):
    """
    What happens to someone who is not in the directory. Reaching the
    directory itself is not this test's business.
    """

    def setUp(self):
        super().setUp()
        app.config["AUTH_STRATEGY"] = "auth_remote_ldap"
        self.addCleanup(
            app.config.__setitem__,
            "LDAP_FALLBACK",
            app.config["LDAP_FALLBACK"],
        )

    def test_a_local_person_falls_back_on_the_local_strategy(self):
        app.config["LDAP_FALLBACK"] = True
        self.assertEqual(self.authenticate()["first_name"], "John")
        self.assertRaises(WrongPasswordException, self.authenticate, "wrong")

    def test_a_local_person_without_a_fallback(self):
        app.config["LDAP_FALLBACK"] = False
        self.assertRaises(UserCantConnectDueToNoFallback, self.authenticate)


class LoginLockoutTestCase(AuthTestCase):
    """
    The burst of wrong passwords that shuts an account, and what reopens
    it.
    """

    def lock(self):
        """
        Put the account at the ceiling, as a burst of wrong passwords
        would.
        """
        auth_service.update_login_failed_attempts(
            self.person_id,
            auth_service.MAX_LOGIN_FAILED_ATTEMPS,
            date_helpers.get_utc_now_datetime(),
        )

    def test_a_wrong_password_counts(self):
        self.assertRaises(WrongPasswordException, self.authenticate, "wrong")
        self.assertEqual(self.failed_attemps(), 1)
        self.assertRaises(WrongPasswordException, self.authenticate, "wrong")
        self.assertEqual(self.failed_attemps(), 2)

    def test_wrong_passwords_in_parallel_all_count(self):
        """
        Each wrong password increments the stored count in the database,
        so concurrent failures all count.
        """
        read_count = auth_service.check_login_failed_attempts

        def read_then_two_failures_land(person):
            count = read_count(person)
            Person.query.filter(Person.id == self.person_id).update(
                {"login_failed_attemps": count + 2},
                synchronize_session=False,
            )
            return count

        with mock.patch.object(
            auth_service,
            "check_login_failed_attempts",
            side_effect=read_then_two_failures_land,
        ):
            self.assertRaises(
                WrongPasswordException, self.authenticate, "wrong"
            )
        self.assertEqual(self.failed_attemps(), 3)

    def test_a_count_left_empty_starts_from_zero(self):
        Person.query.filter(Person.id == self.person_id).update(
            {"login_failed_attemps": None}, synchronize_session=False
        )
        self.assertRaises(WrongPasswordException, self.authenticate, "wrong")
        self.assertEqual(self.failed_attemps(), 1)

    def test_a_right_password_clears_the_count(self):
        self.assertRaises(WrongPasswordException, self.authenticate, "wrong")
        self.authenticate()
        self.assertEqual(self.failed_attemps(), 0)

    def test_a_burst_shuts_the_account(self):
        self.lock()
        persons_service.clear_person_cache()
        # Even with the right password: that is the whole point.
        self.assertRaises(TooManyLoginFailedAttempts, self.authenticate)

    def test_the_lockout_reads_the_row_not_the_session_copy(self):
        """
        The lockout reads the failed login count from the database row,
        not from the person object the request holds.
        """
        cached = Person.get(self.person_id)
        db.session.refresh(cached)
        db.session.expunge(cached)
        self.lock()
        persons_service.clear_person_cache()
        # The request holds it as the current user until it ends.
        identity = db.session.merge(cached, load=False)
        self.assertEqual(identity.login_failed_attemps, 0)
        self.assertRaises(TooManyLoginFailedAttempts, self.authenticate)

    def test_an_elapsed_window_reopens_the_account(self):
        """
        Leaving the counter at its ceiling meant one wrong password
        re-locked the account for another minute, so anyone knowing an
        address could hold it shut at one request a minute, the owner
        included. Rearming costs a fresh burst.
        """
        auth_service.update_login_failed_attempts(
            self.person_id,
            auth_service.MAX_LOGIN_FAILED_ATTEMPS,
            date_helpers.get_utc_now_datetime()
            - auth_service.LOGIN_LOCKOUT_DELAY
            - datetime.timedelta(seconds=1),
        )
        persons_service.clear_person_cache()

        self.authenticate()

        self.assertEqual(self.failed_attemps(), 0)

    def test_an_elapsed_window_closes_the_burst(self):
        """
        The window has to clear the counter, not merely let one request
        through. Left at its ceiling, the next wrong password shuts the
        account for another minute, so anyone knowing an address holds it
        closed at one request a minute.
        """
        auth_service.update_login_failed_attempts(
            self.person_id,
            auth_service.MAX_LOGIN_FAILED_ATTEMPS,
            date_helpers.get_utc_now_datetime()
            - auth_service.LOGIN_LOCKOUT_DELAY
            - datetime.timedelta(seconds=1),
        )
        persons_service.clear_person_cache()

        self.assertRaises(WrongPasswordException, self.authenticate, "wrong")

        self.assertEqual(self.failed_attemps(), 1)
        self.authenticate()

    def test_a_ceiling_without_a_date_reopens_the_account(self):
        """
        The rows that predate the date column carry a count and no date.
        """
        auth_service.update_login_failed_attempts(
            self.person_id, auth_service.MAX_LOGIN_FAILED_ATTEMPS
        )
        Person.get(self.person_id).update({"last_login_failed": None})
        persons_service.clear_person_cache()

        self.authenticate()

        self.assertEqual(self.failed_attemps(), 0)

    def test_update_login_failed_attemps_keeps_the_date_when_none_is_given(
        self,
    ):
        moment = date_helpers.get_utc_now_datetime()
        auth_service.update_login_failed_attempts(self.person_id, 3, moment)
        auth_service.update_login_failed_attempts(self.person_id, 0)
        self.assertIsNotNone(Person.get(self.person_id).last_login_failed)

    def test_the_count_keeps_updated_at(self):
        """
        Kitsu versions the avatar URL with updated_at: the failed login
        counter leaves it alone.
        """
        last_edit = datetime.datetime(2021, 1, 1, 12, 0)
        Person.query.filter(Person.id == self.person_id).update(
            {"updated_at": last_edit}
        )

        self.assertRaises(WrongPasswordException, self.authenticate, "wrong")
        self.assertEqual(self.failed_attemps(), 1)
        self.authenticate()
        self.assertEqual(self.failed_attemps(), 0)
        # The end of a lockout window clears the count through its own call.
        auth_service.update_login_failed_attempts(
            self.person_id,
            auth_service.MAX_LOGIN_FAILED_ATTEMPS,
            date_helpers.get_utc_now_datetime()
            - auth_service.LOGIN_LOCKOUT_DELAY
            - datetime.timedelta(seconds=1),
        )
        persons_service.clear_person_cache()
        self.authenticate()
        self.assertEqual(self.failed_attemps(), 0)

        self.assertEqual(
            Person.query.with_entities(Person.updated_at)
            .filter(Person.id == self.person_id)
            .scalar(),
            last_edit,
        )


class TwoFactorMethodTestCase(AuthTestCase):
    """
    Which methods a person can authenticate with, and what enabling or
    disabling one does to the preferred one and to the recovery codes.
    """

    def enable(self, *methods, preferred=None):
        self.person.update(
            {
                **{f"{method}_enabled": True for method in methods},
                "preferred_two_factor_authentication": preferred or methods[0],
                "otp_recovery_codes": [b"a-code"],
            }
        )
        persons_service.clear_person_cache()
        return self.person

    def test_person_two_factor_authentication_enabled(self):
        self.assertFalse(
            auth_service.person_two_factor_authentication_enabled_raw(
                self.person
            )
        )
        self.enable("email_otp")
        self.assertTrue(
            auth_service.person_two_factor_authentication_enabled_raw(
                self.person
            )
        )
        self.assertTrue(
            auth_service.person_two_factor_authentication_enabled(
                self.person.serialize()
            )
        )

    def test_get_two_factor_authentication_enabled(self):
        """
        A recovery code always works, whatever else is enabled.
        """
        self.assertEqual(
            auth_service.get_two_factor_authentication_enabled(
                self.person.serialize()
            ),
            ["recovery_code"],
        )
        self.enable("totp", "fido")
        self.assertEqual(
            auth_service.get_two_factor_authentication_enabled(
                self.person.serialize()
            ),
            ["recovery_code", "totp", "fido"],
        )

    def test_enabling_a_method_issues_the_recovery_codes_once(self):
        codes = auth_service._enable_two_factor_method(self.person, "totp")
        self.assertEqual(len(codes), 16)
        self.assertEqual(len(self.person.otp_recovery_codes), 16)
        self.assertNotIn(codes[0].encode(), self.person.otp_recovery_codes)
        self.assertEqual(
            self.person.preferred_two_factor_authentication, "totp"
        )

        stored = list(self.person.otp_recovery_codes)
        again = auth_service._enable_two_factor_method(self.person, "fido")
        self.assertIsNone(again)
        self.assertEqual(self.person.otp_recovery_codes, stored)
        # The first method enabled stays the preferred one.
        self.assertEqual(
            self.person.preferred_two_factor_authentication, "totp"
        )

    def test_disabling_the_preferred_method_falls_back(self):
        """
        The fallback order is fixed, and only an enabled method is picked.
        """
        self.enable("totp", "email_otp", preferred="totp")
        self.person.totp_enabled = False

        auth_service._disable_two_factor_method(self.person, "totp")

        self.assertEqual(
            self.person.preferred_two_factor_authentication, "email_otp"
        )

    def test_disabling_another_method_leaves_the_preferred_one(self):
        """
        Disabling a method that was not the preferred one changes nothing.
        The fallback order would have picked fido here, so a fallback that
        runs whatever was disabled shows up.
        """
        self.enable("totp", "email_otp", "fido", preferred="email_otp")
        self.person.totp_enabled = False

        auth_service._disable_two_factor_method(self.person, "totp")

        self.assertEqual(
            self.person.preferred_two_factor_authentication, "email_otp"
        )

    def test_disabling_the_last_method_drops_the_recovery_codes(self):
        self.enable("totp")
        self.person.totp_enabled = False

        auth_service._disable_two_factor_method(self.person, "totp")

        self.assertIsNone(self.person.preferred_two_factor_authentication)
        self.assertIsNone(self.person.otp_recovery_codes)

    def test_unregister_fido_keeps_it_preferred_while_a_key_remains(self):
        """
        Removing one key of two leaves FIDO on, so it stays the preferred
        method: only the last key falls back to another method.
        """
        self.enable("fido", "totp")
        self.person.update(
            {
                "fido_credentials": [
                    {"device_name": "security-key"},
                    {"device_name": "backup-key"},
                ]
            }
        )

        auth_service.unregister_fido(self.person_id, "security-key")

        person = Person.get(self.person_id)
        self.assertTrue(person.fido_enabled)
        self.assertEqual(person.preferred_two_factor_authentication, "fido")
        self.assertEqual(
            [key["device_name"] for key in person.fido_credentials],
            ["backup-key"],
        )

        auth_service.unregister_fido(self.person_id, "backup-key")

        person = Person.get(self.person_id)
        self.assertFalse(person.fido_enabled)
        self.assertEqual(person.preferred_two_factor_authentication, "totp")

    def test_unregister_fido_of_an_unknown_key_changes_nothing(self):
        self.enable("fido", "totp")
        self.person.update(
            {"fido_credentials": [{"device_name": "security-key"}]}
        )

        auth_service.unregister_fido(self.person_id, "lost-key")

        person = Person.get(self.person_id)
        self.assertTrue(person.fido_enabled)
        self.assertEqual(person.preferred_two_factor_authentication, "fido")
        self.assertEqual(len(person.fido_credentials), 1)

    def test_disable_two_factor_authentication_for_person(self):
        """
        The admin escape hatch: it turns every method off at once, for a
        user who lost the device they were enrolled with.
        """
        self.assertRaises(
            TwoFactorAuthenticationNotEnabledException,
            auth_service.disable_two_factor_authentication_for_person,
            self.person_id,
        )

        self.enable("totp")
        self.person.update({"totp_secret": "a-secret"})

        auth_service.disable_two_factor_authentication_for_person(
            self.person_id
        )

        person = Person.get(self.person_id)
        self.assertFalse(
            auth_service.person_two_factor_authentication_enabled_raw(person)
        )
        self.assertIsNone(person.totp_secret)
        self.assertIsNone(person.otp_recovery_codes)
        self.assertIsNone(person.preferred_two_factor_authentication)

    def test_is_user_exempt_from_2fa(self):
        self.addCleanup(
            app.config.__setitem__,
            "TWO_FA_EXEMPT_USERS",
            app.config.get("TWO_FA_EXEMPT_USERS", []),
        )
        app.config["TWO_FA_EXEMPT_USERS"] = [self.email]
        self.assertTrue(
            auth_service.is_user_exempt_from_2fa(self.person.serialize(), app)
        )
        self.assertFalse(
            auth_service.is_user_exempt_from_2fa({"email": "other"}, app)
        )


class TwoFactorCheckTestCase(AuthTestCase):
    """
    Which of the submitted second factors is read, and what a recovery
    code costs.
    """

    def test_a_second_factor_is_required_when_one_is_enabled(self):
        self.person.update(
            {"totp_enabled": True, "otp_recovery_codes": [b"a-code"]}
        )
        persons_service.clear_person_cache()
        with self.assertRaises(MissingOTPException):
            self.authenticate()

    def test_the_missing_factor_names_what_would_be_accepted(self):
        self.person.update(
            {
                "totp_enabled": True,
                "preferred_two_factor_authentication": "totp",
                "otp_recovery_codes": [b"a-code"],
            }
        )
        with self.assertRaises(MissingOTPException) as raised:
            auth_service.check_two_factor_authentication(
                self.person.serialize()
            )
        self.assertEqual(
            raised.exception.args,
            ("totp", ["recovery_code", "totp"]),
        )

    def test_a_second_factor_that_is_not_enabled_is_not_read(self):
        """
        Submitting a code for a method the person never enrolled in must
        not be taken for the enabled one, in either direction: the
        enrolled method decides, never the code that arrived.
        """
        self.person.update({"totp_enabled": True})
        with self.assertRaises(MissingOTPException):
            auth_service.check_two_factor_authentication(
                self.person.serialize(), email_otp="123456"
            )

        self.person.update({"totp_enabled": False, "email_otp_enabled": True})
        with self.assertRaises(MissingOTPException):
            auth_service.check_two_factor_authentication(
                self.person.serialize(), totp="123456"
            )

    def test_a_recovery_code_is_accepted_once(self):
        codes = auth_service.generate_recovery_codes()
        self.person.update(
            {
                "totp_enabled": True,
                "otp_recovery_codes": auth_service.hash_recovery_codes(codes),
            }
        )

        self.assertTrue(
            auth_service.check_two_factor_authentication(
                self.person.serialize(), recovery_code=codes[0]
            )
        )
        self.assertEqual(
            len(Person.get(self.person_id).otp_recovery_codes), 15
        )
        self.assertFalse(
            auth_service.check_recovery_code(
                Person.get(self.person_id).serialize(), codes[0]
            )
        )

    def test_a_wrong_recovery_code_consumes_nothing(self):
        codes = auth_service.generate_recovery_codes()
        self.person.update(
            {
                "totp_enabled": True,
                "otp_recovery_codes": auth_service.hash_recovery_codes(codes),
            }
        )
        self.assertFalse(
            auth_service.check_recovery_code(
                self.person.serialize(), "NOTACODE12"
            )
        )
        self.assertEqual(
            len(Person.get(self.person_id).otp_recovery_codes), 16
        )

    def test_a_wrong_second_factor_counts_as_a_failed_attempt(self):
        self.person.update(
            {
                "totp_enabled": True,
                "otp_recovery_codes": auth_service.hash_recovery_codes(
                    auth_service.generate_recovery_codes()
                ),
            }
        )
        persons_service.clear_person_cache()

        with self.assertRaises(Exception):
            self.authenticate(recovery_code="NOTACODE12")

        self.assertEqual(self.failed_attemps(), 1)

    def test_a_second_factor_is_skipped_when_the_caller_says_so(self):
        """
        Confirming a password before changing it re-authenticates without
        asking for the second factor again.
        """
        self.person.update(
            {"totp_enabled": True, "otp_recovery_codes": [b"a-code"]}
        )
        persons_service.clear_person_cache()
        self.assertEqual(self.authenticate(no_otp=True)["first_name"], "John")


class TokenTestCase(AuthTestCase):
    """
    The token pair a session is made of.
    """

    def test_create_auth_tokens(self):
        """
        The refresh token id rides in the access token claims, so that
        logging out revokes both from the access token alone.
        """
        from flask_jwt_extended import decode_token, get_jti

        with app.test_request_context():
            access_token, refresh_token = auth_service.create_auth_tokens(
                self.person_id
            )
        self.assertEqual(
            decode_token(access_token)["refresh_jti"], get_jti(refresh_token)
        )

    def test_create_auth_tokens_carries_the_given_claims(self):
        from flask_jwt_extended import decode_token

        with app.test_request_context():
            access_token, refresh_token = auth_service.create_auth_tokens(
                self.person_id, {"identity_type": "person"}
            )
        self.assertEqual(decode_token(access_token)["identity_type"], "person")
        self.assertEqual(
            decode_token(refresh_token)["identity_type"], "person"
        )

    def test_revoke_tokens(self):
        auth_service.revoke_tokens(
            app, "access-jti", refresh_jti="refresh-jti"
        )
        self.assertTrue(auth_tokens_store.is_revoked("access-jti"))
        self.assertTrue(auth_tokens_store.is_revoked("refresh-jti"))
        self.assertFalse(auth_tokens_store.is_revoked("other-jti"))

    def test_revoke_tokens_without_a_refresh_token(self):
        auth_service.revoke_tokens(app, "lone-jti")
        self.assertTrue(auth_tokens_store.is_revoked("lone-jti"))

    def test_logout_survives_an_unreachable_store(self):
        """
        The client drops its tokens either way, so a store that cannot be
        written to must not fail the request.
        """
        with app.test_request_context(), mock.patch.object(
            auth_service, "revoke_tokens", side_effect=Exception("down")
        ):
            auth_service.logout("a-jti")

    def test_is_default_password(self):
        app.config["AUTH_STRATEGY"] = "auth_local_classic"
        self.assertTrue(auth_service.is_default_password(app, "default"))
        self.assertFalse(auth_service.is_default_password(app, "other"))
        # A studio that logs in without a password has no default one to
        # be nagged about.
        app.config["AUTH_STRATEGY"] = "auth_local_no_password"
        self.assertFalse(auth_service.is_default_password(app, "default"))

    def test_generate_recovery_codes(self):
        codes = auth_service.generate_recovery_codes()
        self.assertEqual(len(codes), 16)
        self.assertEqual(len(set(codes)), 16)
        self.assertEqual({len(code) for code in codes}, {10})

    def test_hash_recovery_codes(self):
        codes = auth_service.generate_recovery_codes()
        hashes = auth_service.hash_recovery_codes(codes)
        self.assertNotIn(codes[0].encode(), hashes)
        self.assertTrue(auth.check_password(hashes[0], codes[0]))
