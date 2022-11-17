import pyotp
import random
import string
from datetime import datetime, timedelta
import flask_bcrypt as bcrypt

from flask_jwt_extended import get_jti
from ldap3 import Server, Connection, ALL, NTLM, SIMPLE
from ldap3.core.exceptions import (
    LDAPSocketOpenError,
    LDAPInvalidCredentialsResult,
)

from zou.app.services import persons_service
from zou.app.models.person import Person
from zou.app.services.exception import (
    PersonNotFoundException,
    WrongPasswordException,
    WrongUserException,
    NoAuthStrategyConfigured,
    UnactiveUserException,
    UserCantConnectDueToNoFallback,
    TooMuchLoginFailedAttemps,
    MissingOTPException,
    WrongOTPException,
    TOTPAlreadyEnabledException,
    TOTPNotEnabledException,
)
from zou.app.stores import auth_tokens_store
from zou.app.utils import date_helpers
from zou.app.models.person import Person

from sqlalchemy.orm.attributes import flag_modified


def check_auth(app, email, password, otp, no_otp=False):
    """
    Depending on configured strategy, it checks if given email and password
    mach an active user in the database. It raises exceptions adapted to
    encountered error (no auth strategy configured, wrong email, wrong passwor
    or unactive user).
    App is needed as parameter to give access to configuration while avoiding
    cyclic imports.
    """
    if not email:
        raise WrongUserException()
    try:
        person = persons_service.get_person_by_email(email, unsafe=True)
    except PersonNotFoundException:
        try:
            person = persons_service.get_person_by_desktop_login(email)
        except PersonNotFoundException:
            raise WrongUserException()

    if not person.get("active", False):
        raise UnactiveUserException()

    login_failed_attemps = check_login_failed_attemps(person)

    strategy = app.config["AUTH_STRATEGY"]
    try:
        if strategy == "auth_local_classic":
            local_auth_strategy(person, password, app)
        elif strategy == "auth_local_no_password":
            no_password_auth_strategy(person, password, app)
        elif strategy == "auth_remote_ldap":
            ldap_auth_strategy(person, password, app)
        else:
            raise NoAuthStrategyConfigured()
    except WrongPasswordException:
        update_login_failed_attemps(
            person["id"], login_failed_attemps + 1, datetime.now()
        )
        raise WrongPasswordException()

    if not no_otp:
        otp_verifications = []
        if person["totp_enabled"]:
            otp_verifications.append(check_totp)
        if otp_verifications:
            otp_verifications.append(check_recovery_code)
            if not otp:
                raise MissingOTPException()
            otp_verified = False
            for otp_verification in otp_verifications:
                if otp_verification(person, otp):
                    otp_verified = True
                    break
            if not otp_verified:
                update_login_failed_attemps(
                    person["id"], login_failed_attemps + 1, datetime.now()
                )
                raise WrongOTPException()

    if login_failed_attemps > 0:
        update_login_failed_attemps(person["id"], 0)

    if "password" in person:
        del person["password"]

    if "otp_secret" in person:
        del person["otp_secret"]

    if "otp_recovery_codes" in person:
        del person["otp_recovery_codes"]

    return person


def no_password_auth_strategy(person, password, app):
    """
    No password auth strategy
    """
    return person


def local_auth_strategy(person, password, app=None):
    """
    Local strategy just checks that person and passwords are correct the
    traditional way (email is in database and related password hash corresponds
    to given password).
    Password hash comparison is based on BCrypt.
    """
    try:
        password_hash = person["password"] or ""
        if password_hash and bcrypt.check_password_hash(
            password_hash, password
        ):
            return person
        else:
            raise WrongPasswordException()
    except ValueError:
        raise WrongPasswordException()


def ldap_auth_strategy(person, password, app):
    """
    Connect to an active directory server to know if given user can be
    authenticated.
    When person is not from ldap, it can try to connect with default auth
    strategy.
    (only if fallback is activated (via LDAP_FALLBACK flag) in configuration)
    """
    if person["is_generated_from_ldap"]:
        try:
            SSL = app.config["LDAP_SSL"]
            if app.config["LDAP_IS_AD_SIMPLE"]:
                user = "CN=%s,%s" % (
                    person["full_name"],
                    app.config["LDAP_BASE_DN"],
                )
                authentication = SIMPLE
            elif app.config["LDAP_IS_AD"]:
                user = "%s\%s" % (
                    app.config["LDAP_DOMAIN"],
                    person["desktop_login"],
                )
                authentication = NTLM
            else:
                user = "uid=%s,%s" % (
                    person["desktop_login"],
                    app.config["LDAP_BASE_DN"],
                )
                authentication = SIMPLE

            ldap_server = "%s:%s" % (
                app.config["LDAP_HOST"],
                app.config["LDAP_PORT"],
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
                "Cannot connect to LDAP/Active directory server %s "
                % (ldap_server)
            )
            raise LDAPSocketOpenError()

        except LDAPInvalidCredentialsResult:
            app.logger.error(
                "LDAP cannot authenticate user: %s" % person["email"]
            )
            raise WrongPasswordException()

    elif app.config["LDAP_FALLBACK"]:
        return local_auth_strategy(person, password, app)
    else:
        raise UserCantConnectDueToNoFallback()


def check_login_failed_attemps(person):
    """
    Checks that the person has not reached the failed login limit.
    """
    login_failed_attemps = person["login_failed_attemps"]
    if login_failed_attemps is None:
        login_failed_attemps = 0
    if (
        login_failed_attemps >= 5
        and date_helpers.get_datetime_from_string(person["last_login_failed"])
        + timedelta(minutes=1)
        > datetime.now()
    ):
        raise TooMuchLoginFailedAttemps()
    return login_failed_attemps


def update_login_failed_attemps(
    person_id, login_failed_attemps, last_login_failed=None
):
    """
    Update login failed attemps for a person_id.
    """
    person = Person.get(person_id)
    person.login_failed_attemps = login_failed_attemps
    if last_login_failed is not None:
        person.last_login_failed = last_login_failed
    person.commit()
    persons_service.clear_person_cache()
    return person.serialize()


def remove_otp_revovery_code(person_id, recovery_hash):
    """
    Remove an otp recovery code for a person_id.
    """
    person = Person.get(person_id)
    person.otp_recovery_codes.remove(recovery_hash.encode())
    flag_modified(person, "otp_recovery_codes")
    person.commit()
    persons_service.clear_person_cache()
    return person.serialize()


def check_totp(person, totp):
    """
    Check TOTP for a person.
    """
    return pyotp.TOTP(person["otp_secret"]).verify(totp)


def check_recovery_code(person, recovery_code):
    """
    Check recovery code for a person.
    """
    if not person["otp_recovery_codes"]:
        return False
    for recovery_hash in person["otp_recovery_codes"]:
        if bcrypt.check_password_hash(recovery_hash, recovery_code):
            remove_otp_revovery_code(person["id"], recovery_hash)
            return True
    return False


def pre_enable_totp(person_id):
    """
    Pre-enable TOTP for a person.
    """
    person = Person.get(person_id)
    if person.totp_enabled:
        raise TOTPAlreadyEnabledException()
    else:
        person.otp_secret = pyotp.random_base32()
        totp = pyotp.TOTP(person.otp_secret)
        organisation = persons_service.get_organisation()
        totp_provisionning_uri = totp.provisioning_uri(
            name=person.email, issuer_name="Kitsu %s" % organisation["name"]
        )
        person.totp_enabled = False
        person.commit()
        persons_service.clear_person_cache()
        return totp_provisionning_uri, person.otp_secret


def enable_totp(person_id, totp):
    """
    Enable TOTP for a person
    """
    person = Person.get(person_id)
    if person.totp_enabled:
        raise TOTPAlreadyEnabledException()
    elif pyotp.TOTP(person.otp_secret).verify(totp):
        person.totp_enabled = True
        otp_recovery_codes = None
        if not person.otp_recovery_codes:
            otp_recovery_codes = [
                "".join(
                    random.SystemRandom().choice(
                        string.ascii_uppercase + string.digits
                    )
                    for _ in range(10)
                )
                for _ in range(16)
            ]
            person.otp_recovery_codes = [
                bcrypt.generate_password_hash(recovery_code)
                for recovery_code in otp_recovery_codes
            ]
        person.commit()
        persons_service.clear_person_cache()
        return otp_recovery_codes
    else:
        raise WrongOTPException


def disable_totp(person_id, totp):
    """
    Disable TOTP for a person.
    """
    person = Person.get(person_id)
    if not person.totp_enabled:
        raise TOTPNotEnabledException()
    elif pyotp.TOTP(person.otp_secret).verify(totp):
        person.otp_secret = None
        person.otp_recovery_codes = None
        person.totp_enabled = False
        person.commit()
        persons_service.clear_person_cache()
        return True
    else:
        raise WrongOTPException


def register_tokens(app, access_token, refresh_token=None):
    """
    Register access and refresh tokens to auth token store. That way they
    can be used like a session.
    """
    access_jti = get_jti(encoded_token=access_token)
    auth_tokens_store.add(
        access_jti, "false", app.config["JWT_ACCESS_TOKEN_EXPIRES"]
    )

    if refresh_token is not None:
        refresh_jti = get_jti(encoded_token=refresh_token)
        auth_tokens_store.add(
            refresh_jti, "false", app.config["JWT_REFRESH_TOKEN_EXPIRES"]
        )


def revoke_tokens(app, jti):
    """
    Remove access and refresh tokens from auth token store.
    """
    auth_tokens_store.add(jti, "true", app.config["JWT_ACCESS_TOKEN_EXPIRES"])


def is_default_password(app, password):
    return (
        password == "default"
        and app.config["AUTH_STRATEGY"] != "auth_local_no_password"
    )


def generate_reset_token():
    return "".join(
        random.SystemRandom().choice(string.ascii_uppercase + string.digits)
        for _ in range(64)
    )


def check_login_failed_attemps(person):
    login_failed_attemps = person["login_failed_attemps"]
    if login_failed_attemps is None:
        login_failed_attemps = 0
    if (
        login_failed_attemps >= 5
        and date_helpers.get_datetime_from_string(person["last_login_failed"])
        + timedelta(minutes=1)
        > datetime.now()
    ):
        raise TooMuchLoginFailedAttemps()
    return login_failed_attemps
