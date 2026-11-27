import base64
import hashlib
import hmac
import json
import random
import secrets
import string
from datetime import timedelta

import pyotp
from babel.dates import format_datetime
from fido2.utils import bytes2int, int2bytes
from fido2.webauthn import (
    AttestedCredentialData,
    PublicKeyCredentialUserEntity,
)
from flask import current_app, request, session
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jti,
)
from ldap3.core.exceptions import (
    LDAPBindError,
    LDAPInvalidCredentialsResult,
    LDAPSocketOpenError,
)
from sqlalchemy import func
from sqlalchemy.orm.attributes import flag_modified

from zou.app import config
from zou.app.exceptions import (
    EmailOTPAlreadyEnabledException,
    EmailOTPNotEnabledException,
    FIDONoPreregistrationException,
    FIDOServerException,
    InactiveUserException,
    LdapAccountConflictException,
    LdapAmbiguousUserException,
    MissingOTPException,
    NoAuthStrategyConfigured,
    PersonNotFoundException,
    TooManyLoginFailedAttempts,
    TOTPAlreadyEnabledException,
    TOTPNotEnabledException,
    TwoFactorAuthenticationNotEnabledException,
    UserCantConnectDueToNoFallback,
    WrongOTPException,
    WrongPasswordException,
    WrongUserException,
)
from zou.app.models.person import SENSITIVE_FIELDS, Person
from zou.app.services import (
    ldap_service,
    organisation_service,
    persons_service,
    preview_accounts_service,
    templates_service,
)
from zou.app.stores import auth_tokens_store
from zou.app.utils import auth, date_helpers, emails
from zou.app.utils.email_i18n import get_email_translation

MAX_LOGIN_FAILED_ATTEMPS = 5
LOGIN_LOCKOUT_DELAY = timedelta(minutes=1)
APP_LOGIN_CODE_TTL = 60

# The methods that replace the preferred method if it is disabled, in
# order of preference.
TWO_FACTOR_FALLBACKS = {
    "totp": ["fido", "email_otp"],
    "email_otp": ["fido", "totp"],
    "fido": ["totp", "email_otp"],
}

# The hash for the comparison when the address is unknown. Thus a login
# costs the same bcrypt round if the account exists or not. It is built
# on the first use, to keep it out of the import path.
_dummy_password_hash = None


def _spend_password_check_time(password):
    """
    Run a bcrypt comparison that cannot succeed. Without it, the answer
    for an unknown address took a few milliseconds. The answer for a real
    address took about 100 ms, the intentional cost of bcrypt. This
    difference is ten times more than the network jitter. It was enough
    to find the registered addresses from answers that are otherwise
    identical.

    This applies to the local strategy only: an LDAP bind has its own
    time profile.
    """
    global _dummy_password_hash
    if _dummy_password_hash is None:
        _dummy_password_hash = auth.encrypt_password("dummy password")
    try:
        auth.check_password(_dummy_password_hash, password or "")
    except Exception:
        pass


def check_auth(
    app,
    email,
    password,
    totp=None,
    email_otp=None,
    fido_authentication_response=None,
    recovery_code=None,
    no_otp=False,
):
    """
    With the configured strategy, make sure that the given email and
    password match an active user in the database. Then, if a second
    factor is enabled, examine it. For each error, raise the related
    exception:
    - no auth strategy configured
    - wrong email
    - wrong password
    - too many failed attempts
    - inactive user
    - missing or wrong second factor.
    Count a failed attempt for a wrong password or a wrong second factor.
    Reset the counter on success. Return the person as a dict, without its
    sensitive fields.

    Read the account state only after the password is correct. An earlier
    read told "this account exists and is deactivated" to all persons with
    an address and no credential. Thus they could find the registered
    addresses, as with the timing gap that _spend_password_check_time
    closed.

    The app parameter gives access to the configuration and prevents
    cyclic imports.
    """
    if not email:
        raise WrongUserException()
    strategy = app.config["AUTH_STRATEGY"]
    search_bind = (
        strategy == "auth_remote_ldap" and app.config["LDAP_SEARCH_BIND"]
    )
    try:
        person = persons_service.get_person_by_email_desktop_login(email)
    except PersonNotFoundException:
        if not search_bind:
            _spend_password_check_time(password)
            raise WrongUserException()
        # The directory may know this user: the search below decides.
        person = None

    login_failed_attemps = 0
    if person is not None:
        login_failed_attemps = check_login_failed_attempts(person)

    try:
        if strategy == "auth_local_classic":
            local_auth_strategy(person, password, app)
        elif strategy == "auth_local_no_password":
            no_password_auth_strategy(person, password, app)
        elif strategy == "auth_remote_ldap":
            if search_bind and is_search_bind_candidate(person):
                entry, user, ldap_person = find_search_bind_user(
                    person, email, password, app
                )
                if person is None and ldap_person is not None:
                    # Found through another identifier (an UPN, a new
                    # email): the lockout and the failed login counter
                    # apply to it before the password is tried.
                    person = ldap_person
                    login_failed_attemps = check_login_failed_attempts(person)
                person = search_bind_auth_strategy(
                    person, entry, user, password, app
                )
            else:
                ldap_auth_strategy(person, password, app)
        else:
            raise NoAuthStrategyConfigured()
    except WrongPasswordException:
        if person is not None:
            add_login_failed_attempt(person["id"])
        raise WrongPasswordException()

    # After the password, and before the second factor: a deactivated
    # account does not give the list of its enabled 2FA methods.
    if not person.get("active", False):
        raise InactiveUserException()
    if person.get("preview_project_id") is not None and not (
        preview_accounts_service.is_available()
        and preview_accounts_service.is_preview_session_valid(
            persons_service.get_person_raw(person["id"]), None
        )
    ):
        raise InactiveUserException()

    if not no_otp and person_two_factor_authentication_enabled(person):
        if not check_two_factor_authentication(
            person,
            totp,
            email_otp,
            fido_authentication_response,
            recovery_code,
        ):
            add_login_failed_attempt(person["id"])
            raise WrongOTPException()

    if login_failed_attemps > 0:
        update_login_failed_attempts(person["id"], 0)

    # The login route gives this dict to the client. It comes from the
    # unsafe serialization that contains the secrets above. Remove the
    # fields with the list of the model, not with names written here.
    # Thus no sensitive field is missed.
    # Use a copy, because the dict can come directly from the memoize
    # cache.
    return {
        key: value
        for key, value in person.items()
        if key not in SENSITIVE_FIELDS
    }


def no_password_auth_strategy(person, password, app):
    """
    Auth strategy without a password.
    """
    return person


def local_auth_strategy(person, password, app=None):
    """
    Local strategy: make sure that the person and the password are
    correct. The email must be in the database, and its password hash must
    match the given password. The password hash comparison uses BCrypt.
    """
    # If the stored value of an account cannot be compared, the account
    # pays the same bcrypt cost as an unknown address
    # (_spend_password_check_time). An immediate refusal shows a
    # registered address by the response time only. Both cases are
    # usual: a person imported from a CSV has no password, and the LDAP
    # sync stores the literal b"default", which is not a hash.
    password_hash = person["password"] or ""
    if not password_hash:
        _spend_password_check_time(password)
        raise WrongPasswordException()

    try:
        password_matches = auth.check_password(password_hash, password)
    except ValueError:
        _spend_password_check_time(password)
        raise WrongPasswordException()

    if not password_matches:
        raise WrongPasswordException()
    return person


def ldap_auth_strategy(person, password, app):
    """
    Connect to an active directory server to know if the given user can
    be authenticated. If the person is not from LDAP, the default auth
    strategy can try to connect. This occurs only if the LDAP_FALLBACK
    flag is set in the configuration.
    """
    if person["is_generated_from_ldap"]:
        # An empty password makes an unauthenticated bind (RFC 4513,
        # 5.1.2), and some directories accept it. ldap3 refuses it before
        # it sends the bind. The login returned that error as a server
        # failure.
        if not password:
            raise WrongPasswordException()

        from ldap3 import ALL, NTLM, SIMPLE, Connection, Server
        from ldap3.core.exceptions import (
            LDAPInvalidCredentialsResult,
            LDAPSocketOpenError,
        )

        try:
            SSL = app.config["LDAP_SSL"]
            if app.config["LDAP_IS_AD_SIMPLE"]:
                user = f"cn={person['desktop_login']},{app.config['LDAP_BASE_DN']}"
                authentication = SIMPLE
            elif app.config["LDAP_IS_AD"]:
                user = (
                    f"{app.config['LDAP_DOMAIN']}\\{person['desktop_login']}"
                )
                authentication = NTLM
            else:
                user = f"uid={person['desktop_login']},{app.config['LDAP_BASE_DN']}"
                authentication = SIMPLE

            ldap_server = (
                f"{app.config['LDAP_HOST']}:{app.config['LDAP_PORT']}"
            )
            server = Server(ldap_server, get_info=ALL, use_ssl=SSL)
            conn = Connection(
                server,
                user=user,
                password=password,
                authentication=authentication,
                raise_exceptions=True,
            )
            conn.bind()
            return person

        except LDAPSocketOpenError:
            app.logger.error(
                f"Cannot connect to LDAP/Active directory server {ldap_server} "
            )
            raise LDAPSocketOpenError()

        except LDAPInvalidCredentialsResult:
            app.logger.error(
                f"LDAP cannot authenticate user: {person['email']}"
            )
            raise WrongPasswordException()

    elif app.config["LDAP_FALLBACK"]:
        return local_auth_strategy(person, password, app)
    else:
        raise UserCantConnectDueToNoFallback()


def is_search_bind_candidate(person):
    """
    Whether the login of this person goes through the directory search:
    an unknown person or one generated from LDAP. Local and protected
    accounts keep the legacy LDAP strategy and are never touched by it.
    """
    return person is None or (
        person["is_generated_from_ldap"]
        and person["email"] not in config.PROTECTED_ACCOUNTS
    )


def find_search_bind_user(person, identifier, password, app):
    """
    Find the user anywhere under the base DN with the service account and
    resolve the matching person, before any password is tried. Return the
    entry, the user dict built from it and the person (None for a user new
    to Zou).

    A person whose entry is gone from the directory (or out of the group)
    gets deactivated: it was looked for by its LDAP uid, its desktop login
    and the typed identifier, and none matched. The same applies to an
    entry that is disabled or excluded. An LDAP error never deactivates
    anybody: it is raised as is.
    """
    settings = ldap_service.get_settings()
    if not settings["LDAP_USER"]:
        app.logger.error(
            "LDAP_SEARCH_BIND is enabled but LDAP_USER is not set."
        )
        raise NoAuthStrategyConfigured()

    try:
        conn = ldap_service.open_service_connection(settings)
    except LDAPSocketOpenError:
        app.logger.error(
            "Cannot connect to LDAP/Active directory server "
            f"{settings['LDAP_HOST']}:{settings['LDAP_PORT']}"
        )
        raise
    except (LDAPBindError, LDAPInvalidCredentialsResult):
        app.logger.error(
            "LDAP service account bind failed: check LDAP_USER and "
            "LDAP_PASSWORD."
        )
        raise NoAuthStrategyConfigured()
    try:
        if person is None:
            entry = ldap_service.find_user_entry(conn, settings, identifier)
        else:
            entry = ldap_service.find_user_entry(
                conn,
                settings,
                identifier,
                ldap_uid=person["ldap_uid"],
                desktop_login=person["desktop_login"],
            )
    except LdapAmbiguousUserException as exception:
        app.logger.error(f"LDAP login refused: {exception}")
        _spend_password_check_time(password)
        raise WrongUserException()
    finally:
        conn.unbind()

    user = None
    if entry is not None:
        user = ldap_service.entry_to_user(entry, settings)
        if person is None:
            try:
                person = ldap_service.find_ldap_person(user)
            except LdapAccountConflictException:
                # Answered like an unknown user, before the password is
                # tried: the conflict shows in the logs only.
                _spend_password_check_time(password)
                raise WrongUserException()

    # Refused before the password: Active Directory rejects the bind of a
    # disabled account, so its state is never read after it. An excluded
    # account, usually a service account, must receive no bind at all.
    if (
        entry is None
        or not user["active"]
        or ldap_service.is_excluded(settings, user["desktop_login"])
    ):
        if person is not None:
            ldap_service.deactivate_person(person)
        _spend_password_check_time(password)
        raise WrongUserException()
    return entry, user, person


def search_bind_auth_strategy(person, entry, user, password, app):
    """
    Check the password by binding with the found entry, then create or
    update the person of the user and return it, read with the unsafe
    serialization as the person lookup of check_auth does.
    """
    settings = ldap_service.get_settings()
    ldap_service.check_user_password(settings, entry, password)

    try:
        person_id = ldap_service.provision_person(user, person)
    except LdapAccountConflictException:
        raise WrongUserException()
    return persons_service.get_person_raw(person_id).serialize()


def update_login_failed_attempts(
    person_id, login_failed_attemps, last_login_failed=None
):
    """
    Set the failed login counter of a person_id to the given count.

    Do not change the person cache. check_login_failed_attempts reads the
    counter from the row, thus the cached copy can stay different. Also,
    clear_person_cache removes all memoized person searches of the whole
    instance. With a call here, an anonymous caller kept that cache empty
    with a few wrong passwords each minute. The JWT loader reads that
    cache on each authenticated request.

    updated_at also keeps its value: Kitsu uses it as the version of the
    avatar URL.
    """
    values = {
        "login_failed_attemps": login_failed_attemps,
        # Set updated_at to itself. Thus it keeps its value and does not
        # take the onupdate default.
        "updated_at": Person.updated_at,
    }
    if last_login_failed is not None:
        values["last_login_failed"] = last_login_failed
    Person.query.filter(Person.id == person_id).update(
        values, synchronize_session=False
    )
    Person.commit()


def add_login_failed_attempt(person_id):
    """
    Count one more failed login for a person_id, with the current date.
    The database adds it to the stored count, thus all parallel failures
    count. The person cache and updated_at do not change, as in
    update_login_failed_attempts.
    """
    Person.query.filter(Person.id == person_id).update(
        {
            "login_failed_attemps": func.coalesce(
                Person.login_failed_attemps, 0
            )
            + 1,
            "last_login_failed": date_helpers.get_utc_now_datetime(),
            "updated_at": Person.updated_at,
        },
        synchronize_session=False,
    )
    Person.commit()


def check_two_factor_authentication(
    person,
    totp=None,
    email_otp=None,
    fido_authentication_response=None,
    recovery_code=None,
):
    """
    Check the multifactor authentication of a person. If the given code is
    correct, return True. If not, return False. If there is no code for an
    enabled method, raise MissingOTPException.
    """
    if person["totp_enabled"] and totp is not None:
        return check_totp(person, totp)
    elif person["email_otp_enabled"] and email_otp is not None:
        return check_email_otp(person, email_otp)
    elif person["fido_enabled"] and fido_authentication_response is not None:
        return check_fido(person, fido_authentication_response)
    elif recovery_code is not None:
        return check_recovery_code(person, recovery_code)
    else:
        raise MissingOTPException(
            person["preferred_two_factor_authentication"],
            get_two_factor_authentication_enabled(person),
        )


def person_two_factor_authentication_enabled(person):
    """
    Return True if the given person has one or more enabled 2FA methods.
    """
    return (
        person["totp_enabled"]
        or person["email_otp_enabled"]
        or person["fido_enabled"]
    )


def _enable_two_factor_method(person, method):
    """
    Record the given method as enabled. If the person has no recovery
    codes, make them. If there is no preferred method, make this method
    the preferred one. If new recovery codes were made, return them as
    plain text. If not, return None.
    """
    otp_recovery_codes = None
    if not person.otp_recovery_codes:
        otp_recovery_codes = generate_recovery_codes()
        person.otp_recovery_codes = hash_recovery_codes(otp_recovery_codes)
    if not person.preferred_two_factor_authentication:
        person.preferred_two_factor_authentication = method
    return otp_recovery_codes


def _disable_two_factor_method(person, method):
    """
    Update the preferred method after the given method was disabled. Use
    another enabled method. If no method remains, remove the preference
    and the recovery codes. The caller has already disabled the method.
    """
    if not person_two_factor_authentication_enabled_raw(person):
        person.otp_recovery_codes = None
        person.preferred_two_factor_authentication = None
        return
    if person.preferred_two_factor_authentication != method:
        return
    for fallback in TWO_FACTOR_FALLBACKS[method]:
        if getattr(person, f"{fallback}_enabled"):
            person.preferred_two_factor_authentication = fallback
            return


def is_user_exempt_from_2fa(person, app):
    """
    Return True if the user does not have to use 2FA. This applies to a
    preview account, or to an email in TWO_FA_EXEMPT_USERS.
    """
    if person.get("preview_project_id") is not None:
        return True
    exempt_users = app.config.get("TWO_FA_EXEMPT_USERS", [])
    return person.get("email", "") in exempt_users


def person_two_factor_authentication_enabled_raw(person):
    """
    Same as person_two_factor_authentication_enabled, for an active
    record.
    """
    return (
        person.totp_enabled or person.email_otp_enabled or person.fido_enabled
    )


def get_two_factor_authentication_enabled(person):
    """
    Return the list of the 2FA methods that the given person can use to
    authenticate.
    """
    two_factor_authentication_enabled = ["recovery_code"]
    if person["totp_enabled"]:
        two_factor_authentication_enabled.append("totp")
    if person["email_otp_enabled"]:
        two_factor_authentication_enabled.append("email_otp")
    if person["fido_enabled"]:
        two_factor_authentication_enabled.append("fido")
    return two_factor_authentication_enabled


def remove_otp_revovery_code(person_id, recovery_hash):
    """
    Remove an OTP recovery code of a person_id, and clear the person
    cache. Return the person as a dict.
    """
    # recovery_hash can be a str (serialized login path) or bytes (raw ORM
    # value from get_current_user(unsafe=True)). Convert it to the bytes
    # stored in the column.
    if isinstance(recovery_hash, str):
        recovery_hash = recovery_hash.encode()
    person = Person.get(person_id)
    person.otp_recovery_codes.remove(recovery_hash)
    flag_modified(person, "otp_recovery_codes")
    person.commit()
    persons_service.clear_person_cache()
    return person.serialize()


def _remove_spaces(code):
    """
    Return the given 2FA code without the spaces typed in it: authenticator
    apps show a TOTP in two groups of digits, and no code holds a space.
    """
    return "".join(str(code).split())


def check_totp(person, totp):
    """
    Check the TOTP of a person. The spaces typed in the code are ignored.
    """
    return pyotp.TOTP(person["totp_secret"]).verify(
        _remove_spaces(totp), valid_window=1
    )


def check_email_otp(person, email_otp, consume=True):
    """
    Check the email OTP of a person. A correct code works one time only,
    unless consume is False. The spaces typed in the code are ignored.
    """
    count = auth_tokens_store.get(f"email-otp-count-{person['email']}")
    if count is not None:
        if pyotp.HOTP(person["email_otp_secret"]).verify(
            _remove_spaces(email_otp), int(count)
        ):
            if consume:
                auth_tokens_store.delete(f"email-otp-count-{person['email']}")
            return True
    return False


def check_recovery_code(person, recovery_code):
    """
    Check the recovery code of a person. Remove a matching code from the
    person: it works one time only. Codes are made of capital letters and
    digits, so a code typed in lowercase or with spaces matches too.
    """
    recovery_code = _remove_spaces(recovery_code).upper()
    for recovery_hash in person["otp_recovery_codes"]:
        if auth.check_password(recovery_hash, recovery_code):
            remove_otp_revovery_code(person["id"], recovery_hash)
            return True
    return False


def check_fido(person, authentication_response):
    """
    Check the FIDO authentication of a person.
    """
    try:
        state = session.pop(f"fido-state-{person['id']}")
    except KeyError:
        return False
    try:
        # Get fido_credentials from the database: the serialized person
        # does not contain it.
        fido_credentials = Person.get(person["id"]).fido_credentials
        current_app.extensions["fido_server"].authenticate_complete(
            state,
            get_fido_attested_credential_data_from_person(fido_credentials),
            authentication_response,
        )
    except Exception as exception:
        current_app.logger.info(f"FIDO authentication failed: {exception}")
        return False
    return True


def pre_enable_totp(person_id):
    """
    Pre-enable TOTP for a person: store a new secret. Return the
    provisioning URI and the secret.
    """
    person = Person.get(person_id)
    if person.totp_enabled:
        raise TOTPAlreadyEnabledException()

    person.totp_secret = pyotp.random_base32()
    totp = pyotp.TOTP(person.totp_secret)
    organisation = organisation_service.get_organisation()
    totp_provisionning_uri = totp.provisioning_uri(
        name=person.email, issuer_name=f"Kitsu {organisation['name']}"
    )
    person.totp_enabled = False
    person.commit()
    persons_service.clear_person_cache()
    return totp_provisionning_uri, person.totp_secret


def enable_totp(person_id, totp, check_existing_factor=None):
    """
    Enable TOTP for a person. Call check_existing_factor after the new
    code is known to be correct, and before the function stores data. To
    refuse, it raises. If it is called first, it uses a factor for a code
    that fails. Return the new recovery codes. If the person already had
    recovery codes, return None.
    """
    person = Person.get(person_id)
    if person.totp_enabled:
        raise TOTPAlreadyEnabledException()
    if not check_totp(person.serialize(), totp):
        raise WrongOTPException
    if check_existing_factor is not None:
        check_existing_factor()

    person.totp_enabled = True
    otp_recovery_codes = _enable_two_factor_method(person, "totp")
    person.commit()
    persons_service.clear_person_cache()
    return otp_recovery_codes


def disable_totp(person_id):
    """
    Disable TOTP for a person.
    """
    person = Person.get(person_id)
    if not person.totp_enabled:
        raise TOTPNotEnabledException()
    person.totp_enabled = False
    person.totp_secret = None
    _disable_two_factor_method(person, "totp")
    person.commit()
    persons_service.clear_person_cache()
    return True


def pre_enable_email_otp(person_id):
    """
    Pre-enable email OTP for a person. Store a new secret and send a first
    code by email.
    """
    person = Person.get(person_id)
    if person.email_otp_enabled:
        raise EmailOTPAlreadyEnabledException()

    person.email_otp_secret = pyotp.random_base32()
    person.email_otp_enabled = False
    person.commit()
    send_email_otp(person.serialize())
    persons_service.clear_person_cache()
    return True


def enable_email_otp(person_id, email_otp, check_existing_factor=None):
    """
    Enable email OTP for a person. Call check_existing_factor after the
    new code is known to be correct, and before the function stores data.
    To refuse, it raises. Return the new recovery codes. If the person
    already had recovery codes, return None.
    """
    person = Person.get(person_id)
    if person.email_otp_enabled:
        raise EmailOTPAlreadyEnabledException()
    serialized_person = person.serialize()
    # Consume the new code last: if the factor is refused, the code stays
    # usable.
    if not check_email_otp(serialized_person, email_otp, consume=False):
        raise WrongOTPException
    if check_existing_factor is not None:
        check_existing_factor()
    check_email_otp(serialized_person, email_otp)

    person.email_otp_enabled = True
    otp_recovery_codes = _enable_two_factor_method(person, "email_otp")
    person.commit()
    persons_service.clear_person_cache()
    return otp_recovery_codes


def disable_email_otp(person_id):
    """
    Disable email OTP for a person.
    """
    person = Person.get(person_id)
    if not person.email_otp_enabled:
        raise EmailOTPNotEnabledException()
    person.email_otp_enabled = False
    person.email_otp_secret = None
    _disable_two_factor_method(person, "email_otp")
    person.commit()
    persons_service.clear_person_cache()
    return True


def send_email_otp(person):
    """
    Send an email with an OTP, and store the OTP for a check later. The
    email text uses the locale of the person.
    """
    count = random.randint(0, 999999999999)
    otp = pyotp.HOTP(person["email_otp_secret"]).at(count)
    auth_tokens_store.add(
        f"email-otp-count-{person['email']}", count, ttl=60 * 5
    )
    organisation = organisation_service.get_organisation()
    locale = person.get("locale") or config.DEFAULT_LOCALE
    if hasattr(locale, "language"):
        locale = str(locale)
    time_string = format_datetime(
        date_helpers.get_utc_now_datetime(),
        tzinfo=person["timezone"],
        locale=locale,
    )
    person_IP = request.headers.get("X-Forwarded-For", None) or ""
    subject = get_email_translation(
        locale,
        "auth_otp_subject",
        organisation_name=organisation["name"],
    )
    title = get_email_translation(locale, "auth_otp_title")
    html = get_email_translation(
        locale,
        "auth_otp_body",
        first_name=person["first_name"],
        otp=otp,
        time_string=time_string,
        person_IP=person_IP,
    )
    email_html_body = templates_service.generate_html_body(
        title, html, locale=locale
    )
    emails.send_email(subject, email_html_body, person["email"], locale=locale)
    return True


def get_fido_attested_credential_data_from_person(
    fido_person_credentials=None,
):
    """
    Make again the fido2 credential objects from the JSON stored on the
    person.
    """
    credentials = []
    if isinstance(fido_person_credentials, list):
        for credential in fido_person_credentials:
            credentials.append(
                AttestedCredentialData.create(
                    int2bytes(credential["aaguid"], 16),
                    int2bytes(credential["credential_id"]),
                    dict(
                        {
                            1: credential["public_key"]["1"],
                            3: credential["public_key"]["3"],
                            -1: credential["public_key"]["-1"],
                            -2: int2bytes(credential["public_key"]["-2"]),
                            -3: int2bytes(credential["public_key"]["-3"]),
                        }
                    ),
                )
            )
    return credentials


def pre_register_fido(person_id):
    """
    Pre-register a FIDO device for a person. Keep the registration state
    in the session and return the registration options.
    """
    person = Person.get(person_id)
    options, state = current_app.extensions["fido_server"].register_begin(
        PublicKeyCredentialUserEntity(
            id=str(person.id).encode(),
            name=person.email,
            display_name=person.full_name,
        ),
        credentials=get_fido_attested_credential_data_from_person(
            person.fido_credentials
        ),
        user_verification="preferred",
        authenticator_attachment="cross-platform",
    )
    session[f"fido-registration-state-{person.id}"] = state
    return dict(options.public_key)


def register_fido(
    person_id, registration_response, device_name, check_existing_factor=None
):
    """
    Register a FIDO device for a person. Call check_existing_factor after
    the registration is known to be correct, and before the function
    stores data. To refuse, it raises. Return the new recovery codes. If
    the person already had recovery codes, return None.
    """
    person = Person.get(person_id)
    state_key = f"fido-registration-state-{person.id}"
    if state_key not in session:
        raise FIDONoPreregistrationException()
    try:
        auth_data = current_app.extensions["fido_server"].register_complete(
            session[state_key], registration_response
        )
    except Exception:
        session.pop(state_key)
        raise FIDOServerException()
    if check_existing_factor is not None:
        check_existing_factor()
    # Keep the state until here: if the factor is refused, the
    # registration stays pending.
    session.pop(state_key)
    credential_data = {
        "device_name": device_name,
        "aaguid": bytes2int(auth_data.credential_data.aaguid),
        "credential_id": bytes2int(auth_data.credential_data.credential_id),
        "public_key": dict(
            {
                **auth_data.credential_data.public_key,
                -2: bytes2int(auth_data.credential_data.public_key.get(-2)),
                -3: bytes2int(auth_data.credential_data.public_key.get(-3)),
            }
        ),
    }
    if person.fido_credentials is None:
        person.fido_credentials = []
    person.fido_credentials.append(credential_data)
    flag_modified(person, "fido_credentials")
    person.fido_enabled = True
    otp_recovery_codes = _enable_two_factor_method(person, "fido")
    person.commit()
    persons_service.clear_person_cache()
    return otp_recovery_codes


def unregister_fido(person_id, device_name):
    """
    Unregister a FIDO device for a person.
    """
    person = Person.get(person_id)
    for i in range(len(person.fido_credentials)):
        if person.fido_credentials[i]["device_name"] == device_name:
            del person.fido_credentials[i]
            break
    flag_modified(person, "fido_credentials")
    # If keys remain, FIDO and the preferred method stay enabled.
    if len(person.fido_credentials) == 0:
        person.fido_enabled = False
        _disable_two_factor_method(person, "fido")
    person.commit()
    persons_service.clear_person_cache()
    return True


def get_challenge_fido(person_id):
    """
    Return a new FIDO challenge for a person. Keep the authentication
    state in the session and return the options.
    """
    person = Person.get(person_id)
    options, state = current_app.extensions["fido_server"].authenticate_begin(
        credentials=get_fido_attested_credential_data_from_person(
            person.fido_credentials
        ),
    )
    session[f"fido-state-{person.id}"] = state
    return dict(options.public_key)


def disable_two_factor_authentication_for_person(person_id):
    """
    Disable all the 2FA methods of a person and remove their recovery
    codes.
    """
    person = Person.get(person_id)
    if not person_two_factor_authentication_enabled_raw(person):
        raise TwoFactorAuthenticationNotEnabledException()
    person.email_otp_enabled = False
    person.email_otp_secret = None
    person.totp_enabled = False
    person.totp_secret = None
    person.fido_enabled = False
    person.fido_credentials = None
    person.otp_recovery_codes = None
    person.preferred_two_factor_authentication = None
    person.commit()
    persons_service.clear_person_cache()
    return True


def generate_new_recovery_codes(person_id):
    """
    Make new recovery codes for a person.
    """
    person = Person.get(person_id)
    otp_recovery_codes = generate_recovery_codes()
    person.otp_recovery_codes = hash_recovery_codes(otp_recovery_codes)
    flag_modified(person, "otp_recovery_codes")
    person.commit()
    persons_service.clear_person_cache()
    return otp_recovery_codes


def create_auth_tokens(identity, additional_claims=None):
    """
    Create a pair of an access token and a refresh token. The access token
    claims contain the jti of the refresh token. Thus logout can revoke
    the two tokens at the same time.
    """
    if additional_claims is None:
        additional_claims = {}
    refresh_token = create_refresh_token(
        identity=identity, additional_claims=additional_claims
    )
    access_token = create_access_token(
        identity=identity,
        additional_claims={
            **additional_claims,
            "refresh_jti": get_jti(refresh_token),
        },
    )
    return access_token, refresh_token


def create_app_login_code(person_id, code_challenge, skip_2fa_setup=False):
    """
    Store a one-time browser login code for the given PKCE challenge, and
    return it. It stays valid for APP_LOGIN_CODE_TTL seconds.
    """
    code = secrets.token_urlsafe(32)
    auth_tokens_store.add(
        f"app-login-code-{code}",
        json.dumps(
            {
                "person_id": person_id,
                "code_challenge": code_challenge,
                "skip_2fa_setup": skip_2fa_setup,
            }
        ),
        ttl=APP_LOGIN_CODE_TTL,
    )
    return code


def exchange_app_login_code(code, code_verifier):
    """
    Consume a browser login code. Return the person of the code with a new
    token pair. Return None if one of these conditions is true:
    - the code is unknown or expired
    - the verifier does not match its challenge
    - the person is inactive.
    """
    key = f"app-login-code-{code}"
    value = auth_tokens_store.get(key)
    # If two exchanges occur at the same time, only the exchange whose
    # delete removes the key continues. Thus the code is used one time.
    if value is None or auth_tokens_store.delete(key) != 1:
        return None
    data = json.loads(value)

    challenge = (
        base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        )
        .rstrip(b"=")
        .decode()
    )
    if not hmac.compare_digest(challenge, data["code_challenge"]):
        return None

    try:
        person = persons_service.get_person(data["person_id"])
    except PersonNotFoundException:
        return None
    if not person["active"]:
        return None

    additional_claims = {"identity_type": "person"}
    if data["skip_2fa_setup"]:
        additional_claims["skip_2fa_setup"] = True
    access_token, refresh_token = create_auth_tokens(
        person["id"], additional_claims
    )
    return person, access_token, refresh_token


def revoke_tokens(app, jti, refresh_jti=None):
    """
    Add the given token IDs to the auth token blocklist. Each entry stays
    while the token that it revokes is still valid.
    """
    auth_tokens_store.add(jti, "true", app.config["JWT_ACCESS_TOKEN_EXPIRES"])
    if refresh_jti is not None:
        auth_tokens_store.add(
            refresh_jti, "true", app.config["JWT_REFRESH_TOKEN_EXPIRES"]
        )


def is_default_password(app, password):
    """
    Return True if the password is the default password.
    """
    return (
        password == "default"
        and app.config["AUTH_STRATEGY"] != "auth_local_no_password"
    )


def generate_recovery_codes():
    """
    Make recovery codes and return them.
    """
    return [
        "".join(
            random.SystemRandom().choice(
                string.ascii_uppercase + string.digits
            )
            for _ in range(10)
        )
        for _ in range(16)
    ]


def hash_recovery_codes(recovery_codes):
    """
    Hash the given recovery codes and return them.
    """
    return [
        auth.encrypt_password(recovery_code)
        for recovery_code in recovery_codes
    ]


def check_login_failed_attempts(person):
    """
    Return the count to continue from. If the account is in a lockout
    window, raise.

    When a window ends, the burst ends and the counter goes back to zero.
    If the counter stayed at its maximum, one wrong password locked the
    account again for one more minute. Thus a person who knew an address
    could keep the account locked with one request each minute. This
    also locked out the owner with the correct password. Now, a new lock
    needs a new burst.

    Read the counter from the row, not from the person dict. That dict
    comes from a search memoized for two minutes. To keep it current, each
    wrong password had to clear the person cache of the whole instance.
    See update_login_failed_attempts.
    """
    row = (
        Person.query.with_entities(
            Person.login_failed_attemps, Person.last_login_failed
        )
        .filter(Person.id == person["id"])
        .one()
    )
    login_failed_attemps = row.login_failed_attemps or 0
    if login_failed_attemps < MAX_LOGIN_FAILED_ATTEMPS:
        return login_failed_attemps

    last_login_failed = row.last_login_failed
    if last_login_failed is not None:
        locked_until = last_login_failed + LOGIN_LOCKOUT_DELAY
        if locked_until > date_helpers.get_utc_now_datetime():
            raise TooManyLoginFailedAttempts()

    update_login_failed_attempts(person["id"], 0)
    return 0


def logout(jti, refresh_jti=None):
    """
    Revoke the tokens of the current session. If the token store is not
    available, the logout must not fail: the client removes its tokens in
    all cases.
    """
    try:
        revoke_tokens(current_app, jti, refresh_jti=refresh_jti)
    except Exception:
        current_app.logger.warning(
            "The token store is unreachable, the session tokens were not "
            "revoked.",
            exc_info=1,
        )
