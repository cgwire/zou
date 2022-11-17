from datetime import datetime, timedelta
import flask_bcrypt as bcrypt
import random
import string

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
)
from zou.app.stores import auth_tokens_store
from zou.app.utils import date_helpers


def check_auth(app, email, password):
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
            user = local_auth_strategy(person, password, app)
        elif strategy == "auth_local_no_password":
            user = no_password_auth_strategy(person, password, app)
        elif strategy == "auth_remote_ldap":
            user = ldap_auth_strategy(person, password, app)
        else:
            raise NoAuthStrategyConfigured()
    except WrongPasswordException:
        update_login_failed_attemps(
            person["id"], login_failed_attemps + 1, datetime.now()
        )
        raise WrongPasswordException()

    if login_failed_attemps > 0:
        update_login_failed_attemps(person["id"], 0)

    if "password" in user:
        del user["password"]

    return user


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
                SSL = True
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


def update_login_failed_attemps(
    person_id, login_failed_attemps, last_login_failed=None
):
    person = Person.get(person_id)
    person.login_failed_attemps = login_failed_attemps
    if last_login_failed is not None:
        person.last_login_failed = last_login_failed
    person.commit()
    persons_service.clear_person_cache()
    return person.serialize()
