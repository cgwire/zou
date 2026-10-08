from flasgger import swag_from
import hmac
import secrets

from flask import request, jsonify, current_app, redirect, make_response
from flask.views import MethodView
from flask_jwt_extended import (
    jwt_required,
    create_access_token,
    set_access_cookies,
    set_refresh_cookies,
    unset_jwt_cookies,
    unset_refresh_cookies,
    get_jwt,
)

from sqlalchemy.exc import OperationalError, TimeoutError
from babel.dates import format_datetime
from saml2 import entity, client_base

from zou.app import app, config
from zou.app.mixin import ArgsMixin
from zou.app.utils import auth, emails, permissions, date_helpers, validation
from zou.app.blueprints.auth.schemas import (
    AppLoginCodeSchema,
    AppLoginTokenSchema,
    LoginSchema,
    ChangePasswordSchema,
    ResetPasswordSchema,
    SendPasswordResetSchema,
    TotpSchema,
    TwoFactorAuthSchema,
    EmailOtpSchema,
    FidoRegisterSchema,
    FidoUnregisterSchema,
)
from zou.app.utils.email_i18n import get_email_translation
from zou.app.models.person import normalize_country
from zou.app.services import (
    persons_service,
    auth_service,
    events_service,
    templates_service,
)

from zou.app.utils.flask_utils import is_from_browser
from zou.app.utils.saml import get_subject_from_ava, saml_client_for
from zou.app.utils import oidc

from zou.app.stores import auth_tokens_store
from zou.app.exceptions import (
    EmailOTPAlreadyEnabledException,
    EmailOTPNotEnabledException,
    FIDONoPreregistrationException,
    FIDONotEnabledException,
    FIDOServerException,
    MissingOTPException,
    NoAuthStrategyConfigured,
    NoTwoFactorAuthenticationEnabled,
    SSOIdentityMismatchException,
    PersonInProtectedAccounts,
    PersonNotFoundException,
    TooManyLoginFailedAttempts,
    TOTPAlreadyEnabledException,
    TOTPNotEnabledException,
    InactiveUserException,
    UserCantConnectDueToNoFallback,
    WrongOTPException,
    WrongPasswordException,
    WrongUserException,
)

SSO_REFUSED = {
    "error": "This account cannot be signed in to with this identity. "
    "Ask an administrator."
}


def _build_2fa_registration_response(response_data, user_id):
    """
    After a successful 2FA registration, re-emit JWT cookies without
    the requires_2fa_setup claim so the user gets full access.
    """
    additional_claims = {"identity_type": "person"}
    access_token, refresh_token = auth_service.create_auth_tokens(
        user_id, additional_claims
    )
    response_data["access_token"] = access_token
    response_data["refresh_token"] = refresh_token
    response = jsonify(response_data)
    if is_from_browser(request.user_agent):
        set_access_cookies(response, access_token)
        set_refresh_cookies(response, refresh_token)

    current_app.logger.info(
        f"2FA setup completed, JWT refreshed for user {user_id}."
    )
    return response


class AuthenticatedResource(MethodView):

    @jwt_required()
    @swag_from("openapi/AuthenticatedResource_get.yml")
    def get(self):
        """
        Check authentication status
        """
        person = persons_service.get_current_user(relations=True)
        person["fido_devices"] = (
            persons_service.get_current_user_fido_devices()
        )
        organisation = persons_service.get_organisation(
            sensitive=permissions.has_admin_permissions()
        )
        return {
            "authenticated": True,
            "user": person,
            "organisation": organisation,
        }


class LogoutResource(MethodView):

    @jwt_required()
    @permissions.require_person
    @swag_from("openapi/LogoutResource_get.yml")
    def get(self):
        """
        Logout user
        """
        try:
            payload = get_jwt()
            auth_service.logout(payload["jti"], payload.get("refresh_jti"))
        except KeyError:
            return {"Access token not found."}, 500

        logout_data = {"logout": True}

        if is_from_browser(request.user_agent):
            response = jsonify(logout_data)
            unset_jwt_cookies(response)
            return response
        else:
            return logout_data


def _build_login_response(user, email):
    """
    Tokens, cookies and login log of a successful authentication. A user
    the 2FA policy applies to who has not set it up gets restricted
    tokens, and the response says so.
    """
    # Check if 2FA enforcement requires restricted access
    requires_2fa_setup = False
    if app.config["ENFORCE_2FA"]:
        if not auth_service.is_user_exempt_from_2fa(user, app):
            if not auth_service.person_two_factor_authentication_enabled(user):
                requires_2fa_setup = True

    additional_claims = {"identity_type": "person"}
    if requires_2fa_setup:
        additional_claims["requires_2fa_setup"] = True

    access_token, refresh_token = auth_service.create_auth_tokens(
        user["id"], additional_claims
    )

    ip_address = request.environ.get("HTTP_X_REAL_IP", request.remote_addr)

    organisation = persons_service.get_organisation(
        sensitive=user["role"] == "admin"
    )

    # check_auth() serializes the person without relations, so add
    # departments to reach parity with /auth/authenticated.
    user["departments"] = persons_service.get_person(user["id"])["departments"]

    response_data = {
        "user": user,
        "organisation": organisation,
        "login": True,
        "access_token": access_token,
        "refresh_token": refresh_token,
    }
    if requires_2fa_setup:
        response_data["two_factor_authentication_required"] = True

    response = jsonify(response_data)

    if is_from_browser(request.user_agent):
        set_access_cookies(response, access_token)
        set_refresh_cookies(response, refresh_token)
        events_service.create_login_log(user["id"], ip_address, "web")
    else:
        events_service.create_login_log(user["id"], ip_address, "script")
    if requires_2fa_setup:
        current_app.logger.info(
            f"User {email} logged in with restricted"
            " access - 2FA setup required."
        )
    else:
        current_app.logger.info(f"User {email} is logged in.")
    return response


class LoginResource(MethodView, ArgsMixin):

    @swag_from("openapi/LoginResource_post.yml")
    def post(self):
        """
        Login user
        """
        body = validation.validate_request_body(LoginSchema)
        email = body.email
        password = body.password
        try:
            user = auth_service.check_auth(
                app,
                email,
                password,
                body.totp,
                body.email_otp,
                body.fido_authentication_response,
                body.recovery_code,
            )

            if auth_service.is_default_password(app, password):
                token = auth_service.generate_reset_token()
                auth_tokens_store.add(
                    f"reset-token-{email}", token, ttl=3600 * 2
                )
                current_app.logger.info(
                    f"User {email} must change his password."
                )
                return (
                    {
                        "login": False,
                        "default_password": True,
                        "token": token,
                    },
                    400,
                )

            return _build_login_response(user, email)
        except WrongUserException:
            current_app.logger.info(f"User {email} is not registered.")
            return {"login": False, "message": "Wrong email or password."}, 400
        except WrongPasswordException:
            current_app.logger.info(f"User {email} gave a wrong password.")
            return {"login": False, "message": "Wrong email or password."}, 400
        except NoAuthStrategyConfigured:
            current_app.logger.info(
                "Authentication strategy is not properly configured."
            )
            return {"login": False}, 409
        except UserCantConnectDueToNoFallback:
            current_app.logger.info(
                f"User {email} can't login due to no fallback from LDAP."
            )
            return {"login": False}, 400
        except TimeoutError:
            current_app.logger.info("Timeout occurs while logging in.")
            return {"login": False}, 400
        except InactiveUserException:
            current_app.logger.info(f"User {email} is unactive.")
            return (
                {
                    "error": True,
                    "login": False,
                    "unactive": True,
                    "message": "User is unactive, he cannot log in.",
                },
                401,
            )
        except TooManyLoginFailedAttempts:
            current_app.logger.info(
                f"User {email} can't log in due to too many failed login attempts."
            )
            return (
                {
                    "error": True,
                    "login": False,
                    "too_many_failed_login_attemps": True,
                    "message": "Too many failed login attempts, "
                    "retry in a minute.",
                },
                400,
            )
        except MissingOTPException as e:
            current_app.logger.info(
                f"User {email} can't log in due to missing OTP."
            )
            return (
                {
                    "error": True,
                    "login": False,
                    "missing_OTP": True,
                    "message": "A two-factor authentication code is required.",
                    "preferred_two_factor_authentication": e.preferred_two_factor_authentication,
                    "two_factor_authentication_enabled": e.two_factor_authentication_enabled,
                },
                400,
            )
        except WrongOTPException:
            current_app.logger.info(
                f"User {email} can't log in due to wrong OTP."
            )
            return (
                {
                    "error": True,
                    "login": False,
                    "wrong_OTP": True,
                    "message": "Wrong two-factor authentication code.",
                },
                400,
            )
        except OperationalError as exception:
            current_app.logger.error(exception, exc_info=1)
            return (
                {
                    "error": True,
                    "login": False,
                    "message": "Database doesn't seem reachable.",
                },
                500,
            )
        except Exception as exception:
            current_app.logger.error(exception, exc_info=1)
            return {
                "error": True,
                "login": False,
                "message": "A server error occurred. Please contact your administrator.",
            }, 500

    def get_arguments(self):
        body = validation.validate_request_body(LoginSchema)
        return (
            body.email,
            body.password,
            body.totp,
            body.email_otp,
            body.fido_authentication_response,
            body.recovery_code,
        )


class RefreshTokenResource(MethodView):
    @jwt_required(refresh=True)
    @permissions.require_person
    @swag_from("openapi/RefreshTokenResource_get.yml")
    def get(self):
        """
        Refresh access token
        """
        user = persons_service.get_current_user()
        additional_claims = {"identity_type": "person"}

        # The refresh token carries the claims of the login: an SSO session
        # allowed to skip 2FA must not get restricted on refresh, and the
        # new access token keeps the claim.
        if get_jwt().get("skip_2fa_setup"):
            additional_claims["skip_2fa_setup"] = True
        elif app.config["ENFORCE_2FA"]:
            user_unsafe = persons_service.get_current_user(unsafe=True)
            if not auth_service.is_user_exempt_from_2fa(user_unsafe, app):
                if not auth_service.person_two_factor_authentication_enabled(
                    user_unsafe
                ):
                    additional_claims["requires_2fa_setup"] = True

        # Keep the refresh token jti in the new access token so a later
        # logout still revokes the refresh token.
        additional_claims["refresh_jti"] = get_jwt()["jti"]

        access_token = create_access_token(
            identity=user["id"],
            additional_claims=additional_claims,
        )
        if is_from_browser(request.user_agent):
            response = jsonify({"refresh": True})
            set_access_cookies(response, access_token)
            unset_refresh_cookies(response)
            return response
        else:
            return {"access_token": access_token}


class AppLoginCodeResource(MethodView):

    @jwt_required()
    @permissions.require_person
    @swag_from("openapi/AppLoginCodeResource_post.yml")
    def post(self):
        """
        Mint a browser login code
        """
        body = validation.validate_request_body(AppLoginCodeSchema)
        code = auth_service.create_app_login_code(
            persons_service.get_current_user()["id"],
            body.code_challenge,
            bool(get_jwt().get("skip_2fa_setup")),
        )
        return {"code": code}, 201


class AppLoginTokenResource(MethodView):

    @swag_from("openapi/AppLoginTokenResource_post.yml")
    def post(self):
        """
        Trade a browser login code for tokens
        """
        body = validation.validate_request_body(AppLoginTokenSchema)
        result = auth_service.exchange_app_login_code(
            body.code, body.code_verifier
        )
        if result is None:
            return {
                "login": False,
                "message": "Wrong or expired code.",
            }, 400

        user, access_token, refresh_token = result
        ip_address = request.environ.get("HTTP_X_REAL_IP", request.remote_addr)
        events_service.create_login_log(user["id"], ip_address, "script")
        current_app.logger.info(
            f"User {user['email']} is logged in through the browser."
        )
        return {
            "user": user,
            "organisation": persons_service.get_organisation(
                sensitive=user["role"] == "admin"
            ),
            "login": True,
            "access_token": access_token,
            "refresh_token": refresh_token,
        }


class ChangePasswordResource(MethodView, ArgsMixin):

    @jwt_required()
    @permissions.require_person
    @swag_from("openapi/ChangePasswordResource_post.yml")
    def post(self):
        """
        Change user password
        """
        body = validation.validate_request_body(ChangePasswordSchema)

        try:
            user = persons_service.get_current_user()
            auth_service.check_auth(
                app, user["email"], body.old_password, no_otp=True
            )
            auth.validate_password(body.password, body.password_2)
            password = auth.encrypt_password(body.password)
            persons_service.update_password(user["email"], password)
            current_app.logger.info(
                f"User {user['email']} has changed his password"
            )
            organisation = persons_service.get_organisation()
            locale = user.get("locale") or getattr(
                config, "DEFAULT_LOCALE", "en_US"
            )
            if hasattr(locale, "language"):
                locale = str(locale)
            time_string = format_datetime(
                date_helpers.get_utc_now_datetime(),
                tzinfo=user["timezone"],
                locale=locale,
            )
            person_IP = request.headers.get("X-Forwarded-For", None) or ""
            subject = get_email_translation(
                locale,
                "auth_password_changed_subject",
                organisation_name=organisation["name"],
            )
            title = get_email_translation(
                locale, "auth_password_changed_title"
            )
            html = get_email_translation(
                locale,
                "auth_password_changed_body",
                first_name=user["first_name"],
                time_string=time_string,
                person_IP=person_IP,
            )
            email_html_body = templates_service.generate_html_body(
                title, html, locale=locale
            )
            emails.send_email(
                subject, email_html_body, user["email"], locale=locale
            )
            return {"success": True}

        except auth.PasswordsNoMatchException:
            return (
                {
                    "error": True,
                    "message": "Confirmation password doesn't match.",
                },
                400,
            )
        except auth.PasswordTooShortException:
            return {"error": True, "message": "Password is too short."}, 400
        except InactiveUserException:
            return {"error": True, "message": "User is unactive."}, 400
        except WrongPasswordException:
            return {"error": True, "message": "Old password is wrong."}, 400
        except TooManyLoginFailedAttempts:
            # check_auth applies the login lockout here too, so a user who
            # just failed five logins and then changes his password used to
            # get a 500. The caller holds a token for the account, telling
            # him the truth discloses nothing.
            return (
                {
                    "error": True,
                    "message": "Too many failed login attempts.",
                    "too_many_failed_login_attemps": True,
                },
                400,
            )

    def get_arguments(self):
        body = validation.validate_request_body(ChangePasswordSchema)
        return (body.old_password, body.password, body.password_2)


class ResetPasswordResource(MethodView, ArgsMixin):

    @swag_from("openapi/ResetPasswordResource_put.yml")
    def put(self):
        """
        Reset password with token
        """
        body = validation.validate_request_body(ResetPasswordSchema)

        try:
            token_from_store = auth_tokens_store.get(
                f"reset-token-{body.email}"
            )
            if token_from_store and hmac.compare_digest(
                token_from_store, body.token
            ):
                auth.validate_password(body.password, body.password2)
                password = auth.encrypt_password(body.password)
                persons_service.update_password(body.email, password)
                auth_tokens_store.delete(f"reset-token-{body.email}")
                current_app.logger.info(
                    f"User {body.email} has reset his password"
                )
                return {"success": True}
            else:
                return (
                    {"error": True, "message": "Wrong or expired token."},
                    400,
                )

        except auth.PasswordsNoMatchException:
            return (
                {
                    "error": True,
                    "message": "Confirmation password doesn't match.",
                },
                400,
            )
        except auth.PasswordTooShortException:
            return {"error": True, "message": "Password is too short."}, 400
        except InactiveUserException:
            return {"error": True, "message": "User is inactive."}, 400

    @swag_from("openapi/ResetPasswordResource_post.yml")
    def post(self):
        """
        Request password reset
        """
        body = validation.validate_request_body(SendPasswordResetSchema)

        # Always answer the same way whether or not the account exists or is
        # active, so this public endpoint cannot be used to enumerate
        # registered users.
        generic_response = {"success": "Reset token sent"}
        try:
            user = persons_service.get_person_by_email(body.email)
        except PersonNotFoundException:
            return generic_response
        if not user["active"]:
            return generic_response

        token = auth_service.generate_reset_token()
        auth_tokens_store.add(f"reset-token-{body.email}", token, ttl=3600 * 2)
        reset_url = persons_service.build_password_reset_url(body.email, token)
        locale = user.get("locale") or getattr(
            config, "DEFAULT_LOCALE", "en_US"
        )
        if hasattr(locale, "language"):
            locale = str(locale)
        time_string = format_datetime(
            date_helpers.get_utc_now_datetime(),
            tzinfo=user["timezone"],
            locale=locale,
        )
        person_IP = request.headers.get("X-Forwarded-For", None) or ""
        organisation = persons_service.get_organisation()
        subject = get_email_translation(
            locale,
            "auth_password_recovery_subject",
            organisation_name=organisation["name"],
        )
        title = get_email_translation(locale, "auth_password_recovery_title")
        html = get_email_translation(
            locale,
            "auth_password_recovery_body",
            first_name=user["first_name"],
            reset_url=reset_url,
            time_string=time_string,
            person_IP=person_IP,
        )
        email_html_body = templates_service.generate_html_body(
            title, html, locale=locale
        )
        emails.send_email(subject, email_html_body, body.email, locale=locale)
        return {"success": "Reset token sent"}


class TOTPResource(MethodView, ArgsMixin):

    @jwt_required()
    @permissions.require_person
    @swag_from("openapi/TOTPResource_put.yml")
    def put(self):
        """
        Pre-enable TOTP
        """
        try:
            totp_provisionning_uri, totp_secret = auth_service.pre_enable_totp(
                persons_service.get_current_user()["id"]
            )
            return {
                "totp_provisionning_uri": totp_provisionning_uri,
                "otp_secret": totp_secret,
            }
        except TOTPAlreadyEnabledException:
            return (
                {"error": True, "message": "TOTP already enabled."},
                400,
            )

    @jwt_required()
    @permissions.require_person
    @swag_from("openapi/TOTPResource_post.yml")
    def post(self):
        """
        Enable TOTP
        """
        body = validation.validate_request_body(TotpSchema)

        try:
            current_user = persons_service.get_current_user()
            otp_recovery_codes = auth_service.enable_totp(
                current_user["id"], body.totp
            )
            return _build_2fa_registration_response(
                {"otp_recovery_codes": otp_recovery_codes},
                current_user["id"],
            )
        except TOTPAlreadyEnabledException:
            return (
                {"error": True, "message": "TOTP already enabled."},
                400,
            )
        except WrongOTPException:
            return (
                {
                    "error": True,
                    "message": "TOTP verification failed.",
                    "wrong_OTP": True,
                },
                400,
            )

    @jwt_required()
    @permissions.require_person
    @swag_from("openapi/TOTPResource_delete.yml")
    def delete(self):
        """
        Disable TOTP
        """
        body = validation.validate_request_body(TwoFactorAuthSchema)

        try:
            person = persons_service.get_current_user(unsafe=True)
            if not auth_service.person_two_factor_authentication_enabled(
                person
            ):
                raise TOTPNotEnabledException
            if not auth_service.check_two_factor_authentication(
                person,
                body.totp,
                body.email_otp,
                body.fido_authentication_response,
                body.recovery_code,
            ):
                raise WrongOTPException
            auth_service.disable_totp(person["id"])
            return {"success": True}
        except TOTPNotEnabledException:
            return (
                {"error": True, "message": "TOTP not enabled."},
                400,
            )
        except (WrongOTPException, MissingOTPException):
            return (
                {
                    "error": True,
                    "message": "OTP verification failed.",
                    "wrong_OTP": True,
                },
                400,
            )


class EmailOTPResource(MethodView, ArgsMixin):

    @swag_from("openapi/EmailOTPResource_get.yml")
    def get(self):
        """
        Send email OTP
        """
        args = self.get_args(
            [
                ("email", None, True),
            ],
            location="values",
        )

        # Answer with the same status and the same body whether or not the
        # account exists, is active and has OTP by email enabled. This used
        # to answer 404 "User not found.", 400 "OTP by email not enabled."
        # and 200, which told the three apart in a single unauthenticated
        # request. Response time still tracks the one branch that mails the
        # OTP, emails.send_email talking SMTP synchronously.
        generic_response = {"success": True}
        try:
            person = persons_service.get_person_by_email_desktop_login(
                args["email"]
            )
        except PersonNotFoundException:
            return generic_response
        if not person["active"] or not person["email_otp_enabled"]:
            return generic_response

        auth_service.send_email_otp(person)
        return generic_response

    @jwt_required()
    @permissions.require_person
    @swag_from("openapi/EmailOTPResource_put.yml")
    def put(self):
        """
        Pre-enable email OTP
        """
        try:
            auth_service.pre_enable_email_otp(
                persons_service.get_current_user()["id"]
            )
            return {"success": True}
        except EmailOTPAlreadyEnabledException:
            return (
                {"error": True, "message": "OTP by email already enabled."},
                400,
            )

    @jwt_required()
    @permissions.require_person
    @swag_from("openapi/EmailOTPResource_post.yml")
    def post(self):
        """
        Enable email OTP
        """
        body = validation.validate_request_body(EmailOtpSchema)

        try:
            current_user = persons_service.get_current_user()
            otp_recovery_codes = auth_service.enable_email_otp(
                current_user["id"],
                body.email_otp,
            )
            return _build_2fa_registration_response(
                {"otp_recovery_codes": otp_recovery_codes},
                current_user["id"],
            )
        except EmailOTPAlreadyEnabledException:
            return (
                {"error": True, "message": "OTP by email already enabled."},
                400,
            )
        except WrongOTPException:
            return (
                {
                    "error": True,
                    "message": "OTP by email verification failed.",
                    "wrong_OTP": True,
                },
                400,
            )

    @jwt_required()
    @permissions.require_person
    @swag_from("openapi/EmailOTPResource_delete.yml")
    def delete(self):
        """
        Disable email OTP
        """
        body = validation.validate_request_body(TwoFactorAuthSchema)

        try:
            person = persons_service.get_current_user(unsafe=True)
            if not auth_service.person_two_factor_authentication_enabled(
                person
            ):
                raise EmailOTPNotEnabledException
            if not auth_service.check_two_factor_authentication(
                person,
                body.totp,
                body.email_otp,
                body.fido_authentication_response,
                body.recovery_code,
            ):
                raise WrongOTPException
            auth_service.disable_email_otp(person["id"])
            return {"success": True}
        except EmailOTPNotEnabledException:
            return (
                {"error": True, "message": "OTP by email not enabled."},
                400,
            )
        except (WrongOTPException, MissingOTPException):
            return (
                {
                    "error": True,
                    "message": "OTP verification failed.",
                    "wrong_OTP": True,
                },
                400,
            )


class FIDOResource(MethodView, ArgsMixin):
    """
    Resource to allow a user to register/unregister FIDO device or to get a
    challenge for a FIDO device.
    """

    @swag_from("openapi/FIDOResource_get.yml")
    def get(self):
        """
        Get FIDO challenge
        """
        args = self.get_args(
            [
                ("email", None, True),
            ],
            location="values",
        )

        # An unknown address, a deactivated account and an account without
        # FIDO all get the same answer, so this public endpoint does not
        # tell a registered address from an unknown one. It used to answer
        # 404 "User not found." to the first and 400 to the second. What a
        # challenge still discloses is that the account has FIDO enabled;
        # hiding that too would mean handing out a decoy challenge no
        # authenticator could ever honour.
        try:
            person = persons_service.get_person_by_email_desktop_login(
                args["email"]
            )
        except PersonNotFoundException:
            person = None

        if (
            person is None
            or not person["active"]
            or not person["fido_enabled"]
        ):
            return {"error": True, "message": "FIDO not enabled."}, 400

        return auth_service.get_challenge_fido(person["id"])

    @jwt_required()
    @permissions.require_person
    @swag_from("openapi/FIDOResource_put.yml")
    def put(self):
        """
        Pre-register FIDO device
        """
        return auth_service.pre_register_fido(
            persons_service.get_current_user()["id"]
        )

    @jwt_required()
    @permissions.require_person
    @swag_from("openapi/FIDOResource_post.yml")
    def post(self):
        """
        Register FIDO device
        """
        try:
            body = validation.validate_request_body(FidoRegisterSchema)

            current_user = persons_service.get_current_user()
            otp_recovery_codes = auth_service.register_fido(
                current_user["id"],
                body.registration_response,
                body.device_name,
            )
            return _build_2fa_registration_response(
                {"otp_recovery_codes": otp_recovery_codes},
                current_user["id"],
            )
        except FIDONoPreregistrationException:
            return (
                {"error": True, "message": "No preregistration before."},
                400,
            )
        except FIDOServerException:
            return (
                {
                    "error": True,
                    "message": "FIDO server exception your registration response is probly wrong.",
                },
                400,
            )

    @jwt_required()
    @permissions.require_person
    @swag_from("openapi/FIDOResource_delete.yml")
    def delete(self):
        """
        Unregister FIDO device
        """
        body = validation.validate_request_body(FidoUnregisterSchema)

        try:
            person = persons_service.get_current_user(unsafe=True)
            if not person["fido_enabled"]:
                raise FIDONotEnabledException
            if not auth_service.check_two_factor_authentication(
                person,
                body.totp,
                body.email_otp,
                body.fido_authentication_response,
                body.recovery_code,
            ):
                raise WrongOTPException
            auth_service.unregister_fido(person["id"], body.device_name)
            return {"success": True}
        except (WrongOTPException, MissingOTPException):
            return (
                {"error": True, "message": "Wrong OTP."},
                400,
            )
        except FIDONotEnabledException:
            return (
                {"error": True, "message": "FIDO not enabled."},
                400,
            )


class RecoveryCodesResource(MethodView, ArgsMixin):

    @jwt_required()
    @permissions.require_person
    @swag_from("openapi/RecoveryCodesResource_put.yml")
    def put(self):
        """
        Generate recovery codes
        """
        body = validation.validate_request_body(TwoFactorAuthSchema)

        try:
            person = persons_service.get_current_user(unsafe=True)
            if not auth_service.person_two_factor_authentication_enabled(
                person
            ):
                raise NoTwoFactorAuthenticationEnabled
            if not auth_service.check_two_factor_authentication(
                person,
                body.totp,
                body.email_otp,
                body.fido_authentication_response,
                body.recovery_code,
            ):
                raise WrongOTPException
            otp_recovery_codes = auth_service.generate_new_recovery_codes(
                person["id"]
            )
            return {"otp_recovery_codes": otp_recovery_codes}
        except WrongOTPException:
            return (
                {
                    "error": True,
                    "message": "OTP verification failed.",
                    "wrong_OTP": True,
                },
                400,
            )
        except NoTwoFactorAuthenticationEnabled:
            return (
                {
                    "error": True,
                    "message": "No two factor authentication enabled.",
                },
                400,
            )


def link_sso_person(protocol, issuer, subject, email, create_info):
    """
    First login of an identity: bind it to the person holding its email,
    created when there is none. A protected account is never reached this
    way, an administrator binds it explicitly.
    """
    try:
        user = persons_service.get_person_by_email(email)
        if user["email"] in config.PROTECTED_ACCOUNTS:
            raise PersonInProtectedAccounts()
    except PersonNotFoundException:
        random_password = auth.encrypt_password(secrets.token_urlsafe(48))
        user = persons_service.create_person(
            email, random_password, **create_info
        )
    persons_service.link_sso_identity(user["id"], protocol, issuer, subject)
    return user


class SAMLSSOResource(MethodView, ArgsMixin):
    @swag_from("openapi/SAMLSSOResource_post.yml")
    def post(self):
        """
        SAML SSO login
        """
        if not config.SAML_ENABLED:
            return {"error": "SAML is not enabled."}, 400
        authn_response = current_app.extensions[
            "saml_client"
        ].parse_authn_request_response(
            request.form["SAMLResponse"], entity.BINDING_HTTP_POST
        )
        authn_response.get_identity()
        email = authn_response.get_subject().text
        person_info = {
            k: (
                " ".join(v)
                if isinstance(v, list)
                and k in ["first_name", "last_name", "country"]
                else v
            )
            for k, v in authn_response.ava.items()
            if k
            in [
                "first_name",
                "last_name",
                "phone",
                "departments",
                "studio_id",
                "country",
            ]
        }
        # Align the country with its stored canonical form so an unchanged
        # value does not re-trigger an update on every login. An empty value
        # clears the stored country (the IdP is authoritative), but a
        # malformed value is dropped so a transient bad assertion neither
        # wipes a previously stored valid code nor breaks the SSO sign-in.
        if "country" in person_info:
            is_valid, normalized = normalize_country(person_info["country"])
            if is_valid:
                person_info["country"] = normalized
            else:
                del person_info["country"]
        try:
            user = self.get_person(authn_response, email, person_info)
        except (
            PersonNotFoundException,
            SSOIdentityMismatchException,
            PersonInProtectedAccounts,
        ):
            current_app.logger.warning(
                "SAML sign-in refused: the account is not bound to this "
                "identity.",
                extra={"email": email},
            )
            return SSO_REFUSED, 400
        for k, v in person_info.items():
            if user.get(k) != v:
                persons_service.update_person(
                    user["id"], person_info, bypass_protected_accounts=True
                )
                break

        response = make_response(
            redirect(f"{config.DOMAIN_PROTOCOL}://{config.DOMAIN_NAME}")
        )

        if user["active"]:
            # Honour 2FA enforcement unless SAML sessions are configured
            # to skip it (e.g. when the identity provider already
            # enforces MFA), mirroring the OIDC callback.
            requires_2fa_setup = False
            if config.ENFORCE_2FA and not config.SAML_SKIP_2FA:
                if not auth_service.is_user_exempt_from_2fa(user, app):
                    if not auth_service.person_two_factor_authentication_enabled(
                        user
                    ):
                        requires_2fa_setup = True

            additional_claims = {"identity_type": "person"}
            if requires_2fa_setup:
                additional_claims["requires_2fa_setup"] = True
            if config.SAML_SKIP_2FA:
                additional_claims["skip_2fa_setup"] = True

            access_token, refresh_token = auth_service.create_auth_tokens(
                user["id"], additional_claims
            )

            ip_address = request.environ.get(
                "HTTP_X_REAL_IP", request.remote_addr
            )

            set_access_cookies(response, access_token)
            set_refresh_cookies(response, refresh_token)
            events_service.create_login_log(user["id"], ip_address, "web")

        return response

    def get_person(self, authn_response, email, person_info):
        """
        Return the person to sign in. With SAML_SUBJECT_ATTRIBUTE set, it is
        the one bound to the issuer and subject of the assertion: the NameID
        email is mutable, it only finds the account on the first login.
        Without it, SAML carries no stable id and the email is all there is.
        """
        if not config.SAML_SUBJECT_ATTRIBUTE:
            try:
                return persons_service.get_person_by_email(email)
            except PersonNotFoundException:
                random_password = auth.encrypt_password(
                    secrets.token_urlsafe(48)
                )
                return persons_service.create_person(
                    email, random_password, **person_info
                )
        issuer = authn_response.issuer()
        subject = get_subject_from_ava(authn_response.ava)
        if not issuer or not subject:
            # An assertion without the attribute is refused, not matched by
            # email: dropping it would otherwise be a way around the binding.
            raise PersonNotFoundException()
        try:
            return persons_service.get_person_by_sso_identity(
                "saml", issuer, subject
            )
        except PersonNotFoundException:
            return link_sso_person("saml", issuer, subject, email, person_info)


class SAMLLoginResource(MethodView, ArgsMixin):

    @swag_from("openapi/SAMLLoginResource_get.yml")
    def get(self):
        """
        SAML SSO login redirect
        """
        if not config.SAML_ENABLED:
            return {"error": "SAML is not enabled."}, 400

        try:
            _, info = current_app.extensions[
                "saml_client"
            ].prepare_for_authenticate()
        except client_base.SAMLError:
            # retry with new client
            current_app.extensions["saml_client"] = saml_client_for(
                config.SAML_METADATA_URL
            )
            _, info = current_app.extensions[
                "saml_client"
            ].prepare_for_authenticate()

        redirect_url = None

        # Select the IdP URL to send the AuthN request to
        for key, value in info["headers"]:
            if key == "Location":
                redirect_url = value

        return redirect(redirect_url, code=302)


class OIDCLoginResource(MethodView, ArgsMixin):
    @swag_from("openapi/OIDCLoginResource_get.yml")
    def get(self):
        """
        OIDC SSO login redirect
        """
        if not config.OIDC_ENABLED:
            return {"error": "OIDC is not enabled."}, 400

        redirect_uri = (
            f"{config.DOMAIN_PROTOCOL}://{config.DOMAIN_NAME}"
            "/api/auth/oidc/callback"
        )
        return oidc.get_oidc_client().authorize_redirect(redirect_uri)


class OIDCCallbackResource(MethodView, ArgsMixin):
    @swag_from("openapi/OIDCCallbackResource_get.yml")
    def get(self):
        """
        OIDC SSO callback
        """
        if not config.OIDC_ENABLED:
            return {"error": "OIDC is not enabled."}, 400

        client = oidc.get_oidc_client()
        try:
            token = client.authorize_access_token(
                claims_options=oidc.get_id_token_claims_options(client)
            )
        except Exception:
            current_app.logger.exception("OIDC token exchange failed.")
            return {"error": "OIDC authentication failed."}, 400
        claims = token.get("userinfo") or {}

        issuer = claims.get("iss")
        subject = claims.get("sub")
        if not issuer or not subject:
            return {"error": "OIDC authentication failed."}, 400

        # The email claim is mutable and set by the provider's
        # administrators: it only finds the account on the first login,
        # then the issuer and subject, which never change, identify it.
        try:
            user = persons_service.get_person_by_sso_identity(
                "oidc", issuer, subject
            )
        except PersonNotFoundException:
            user = None
            email = oidc.get_email_from_claims(claims)
            if not email:
                return {
                    "error": "No email claim returned by the provider."
                }, 400
            if not oidc.is_email_verified(claims):
                return {"error": "Email address is not verified."}, 400

        # Some providers (notably Azure AD/Entra ID) omit name claims from the
        # ID token and only expose them on the userinfo endpoint. Fetch it as a
        # best-effort fallback when the token carried no usable name claims; a
        # failure here must not block an otherwise valid login.
        if not oidc.map_claims(claims):
            try:
                userinfo = client.userinfo(token=token)
                # OIDC Core 5.3.2: a response for another subject must
                # not be used.
                if userinfo.get("sub") == subject:
                    claims = {**userinfo, **claims}
            except Exception:
                current_app.logger.exception(
                    "OIDC userinfo fetch failed; proceeding without it."
                )

        person_info = oidc.map_claims(claims)

        if user is None:
            # first_name/last_name are required by create_person; default them
            # in case the provider did not return the corresponding claims.
            create_info = {"first_name": "", "last_name": "", **person_info}
            try:
                user = link_sso_person(
                    "oidc", issuer, subject, email, create_info
                )
            except (SSOIdentityMismatchException, PersonInProtectedAccounts):
                current_app.logger.warning(
                    "OIDC sign-in refused: the account is not bound to "
                    "this identity.",
                    extra={"email": email, "issuer": issuer},
                )
                return SSO_REFUSED, 400
        for k, v in person_info.items():
            if user.get(k) != v:
                persons_service.update_person(
                    user["id"], person_info, bypass_protected_accounts=True
                )
                break

        response = make_response(
            redirect(f"{config.DOMAIN_PROTOCOL}://{config.DOMAIN_NAME}")
        )

        if user["active"]:
            # Honour 2FA enforcement unless OIDC sessions are configured to
            # skip it (e.g. when the identity provider already enforces MFA).
            requires_2fa_setup = False
            if config.ENFORCE_2FA and not config.OIDC_SKIP_2FA:
                if not auth_service.is_user_exempt_from_2fa(user, app):
                    if not auth_service.person_two_factor_authentication_enabled(
                        user
                    ):
                        requires_2fa_setup = True

            additional_claims = {"identity_type": "person"}
            if requires_2fa_setup:
                additional_claims["requires_2fa_setup"] = True
            if config.OIDC_SKIP_2FA:
                additional_claims["skip_2fa_setup"] = True

            access_token, refresh_token = auth_service.create_auth_tokens(
                user["id"], additional_claims
            )

            ip_address = request.environ.get(
                "HTTP_X_REAL_IP", request.remote_addr
            )

            set_access_cookies(response, access_token)
            set_refresh_cookies(response, refresh_token)
            events_service.create_login_log(user["id"], ip_address, "web")

        return response
