import urllib.parse

from flask import request, jsonify, current_app, redirect, make_response
from flask_restful import Resource
from flask_principal import (
    Identity,
    AnonymousIdentity,
    identity_changed,
)
from flask_jwt_extended import (
    jwt_required,
    create_access_token,
    create_refresh_token,
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
from zou.app.utils import auth, emails, permissions, date_helpers
from zou.app.services import (
    persons_service,
    auth_service,
    events_service,
    templates_service,
)

from zou.app.utils.flask import is_from_browser
from zou.app.utils.saml import saml_client_for

from zou.app.stores import auth_tokens_store
from zou.app.services.exception import (
    EmailOTPAlreadyEnabledException,
    EmailOTPNotEnabledException,
    FIDONoPreregistrationException,
    FIDONotEnabledException,
    FIDOServerException,
    MissingOTPException,
    NoAuthStrategyConfigured,
    NoTwoFactorAuthenticationEnabled,
    PersonNotFoundException,
    TooMuchLoginFailedAttemps,
    TOTPAlreadyEnabledException,
    TOTPNotEnabledException,
    UnactiveUserException,
    UserCantConnectDueToNoFallback,
    WrongOTPException,
    WrongPasswordException,
    WrongUserException,
)


class AuthenticatedResource(Resource):

    @jwt_required()
    def get(self):
        """
        Check authentication status
        ---
        description: Returns information if the user is authenticated.
          It can be used by third party tools, especially browser frontend,
          to know if current user is still logged in.
        tags:
            - Authentication
        responses:
          200:
            description: User authenticated
          401:
            description: Person not found
        """
        person = persons_service.get_current_user(relations=True)
        organisation = persons_service.get_organisation(
            sensitive=permissions.has_admin_permissions()
        )
        return {
            "authenticated": True,
            "user": person,
            "organisation": organisation,
        }


class LogoutResource(Resource):

    @jwt_required()
    @permissions.require_person
    def get(self):
        """
        Logout user
        ---
        description: Log user out by revoking auth tokens. Once logged out, current user cannot access the API anymore.
        tags:
            - Authentication
        responses:
          200:
            description: Logout successful
        """
        try:
            auth_service.logout(get_jwt()["jti"])
            identity_changed.send(
                current_app._get_current_object(), identity=AnonymousIdentity()
            )
        except KeyError:
            return {"Access token not found."}, 500

        logout_data = {"logout": True}

        if is_from_browser(request.user_agent):
            response = jsonify(logout_data)
            unset_jwt_cookies(response)
            return response
        else:
            return logout_data


class LoginResource(Resource, ArgsMixin):

    def post(self):
        """
        Login user
        ---
        description: Log in user by creating and registering auth tokens.
          Login is based on email and password. If no user matches given email
          It fallbacks to a desktop ID. It is useful for desktop tools that
          don't know user email.
          It is also possible to login with TOTP, Email OTP, FIDO and recovery
          code.
        tags:
            - Authentication
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  email:
                    type: string
                    format: email
                    example: admin@example.com
                    description: User email address
                  password:
                    type: string
                    format: password
                    example: mysecretpassword
                    description: User password
                    required: true
                  totp:
                    type: string
                    example: 123456
                    description: TOTP verification code for two-factor authentication
                    required: false
                  email_otp:
                    type: string
                    example: 123456
                    description: Email OTP verification code for two-factor authentication
                  fido_authentication_response:
                    type: object
                    description: FIDO authentication response for WebAuth
                  recovery_code:
                    type: string
                    example: ABCD-EFGH-IJKL-MNOP
                    description: Recovery code for two-factor authentication
                required:
                  - email
                  - password
        responses:
          200:
            description: Login successful
          400:
            description: Login failed
        """
        (
            email,
            password,
            totp,
            email_otp,
            fido_authentication_response,
            recovery_code,
        ) = self.get_arguments()
        try:
            user = auth_service.check_auth(
                app,
                email,
                password,
                totp,
                email_otp,
                fido_authentication_response,
                recovery_code,
            )

            if auth_service.is_default_password(app, password):
                token = auth_service.generate_reset_token()
                auth_tokens_store.add(
                    "reset-token-%s" % email, token, ttl=3600 * 2
                )
                current_app.logger.info(
                    "User %s must change his password." % email
                )
                return (
                    {
                        "login": False,
                        "default_password": True,
                        "token": token,
                    },
                    400,
                )

            access_token = create_access_token(
                identity=user["id"],
                additional_claims={
                    "identity_type": "person",
                },
            )
            refresh_token = create_refresh_token(
                identity=user["id"],
                additional_claims={
                    "identity_type": "person",
                },
            )
            identity_changed.send(
                current_app._get_current_object(),
                identity=Identity(user["id"], "person"),
            )

            ip_address = request.environ.get(
                "HTTP_X_REAL_IP", request.remote_addr
            )

            organisation = persons_service.get_organisation(
                sensitive=user["role"] != "admin"
            )

            response = jsonify(
                {
                    "user": user,
                    "organisation": organisation,
                    "login": True,
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                }
            )

            if is_from_browser(request.user_agent):
                set_access_cookies(response, access_token)
                set_refresh_cookies(response, refresh_token)
                events_service.create_login_log(user["id"], ip_address, "web")
            else:
                events_service.create_login_log(
                    user["id"], ip_address, "script"
                )
            current_app.logger.info(f"User {email} is logged in.")
            return response
        except WrongUserException:
            current_app.logger.info(f"User {email} is not registered.")
            return {"login": False}, 400
        except WrongPasswordException:
            current_app.logger.info(f"User {email} gave a wrong password.")
            return {"login": False}, 400
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
        except UnactiveUserException:
            current_app.logger.info(f"User {email} is unactive.")
            return (
                {
                    "error": True,
                    "login": False,
                    "message": "User is unactive, he cannot log in.",
                },
                401,
            )
        except TooMuchLoginFailedAttemps:
            current_app.logger.info(
                f"User {email} can't log in due to too much login failed attemps."
            )
            return (
                {
                    "error": True,
                    "login": False,
                    "too_many_failed_login_attemps": True,
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
            if hasattr(exception, "message"):
                message = exception.message
            else:
                message = str(exception)
            return {"error": True, "login": False, "message": message}, 500

    def get_arguments(self):
        args = self.get_args(
            [
                {
                    "name": "email",
                    "required": True,
                    "help": "User email is missing.",
                },
                ("password", "default"),
                "totp",
                "email_otp",
                ("fido_authentication_response", None, False, dict),
                "recovery_code",
            ]
        )

        return (
            args["email"],
            args["password"],
            args["totp"],
            args["email_otp"],
            args["fido_authentication_response"],
            args["recovery_code"],
        )


class RefreshTokenResource(Resource):
    @jwt_required(refresh=True)
    @permissions.require_person
    def get(self):
        """
        Refresh access token
        ---
        description: Tokens are considered outdated every two weeks.
          This route allows to extend their lifetime before they get outdated.
        tags:
            - Authentication
        responses:
          200:
            description: Access Token
        """
        user = persons_service.get_current_user()
        access_token = create_access_token(
            identity=user["id"],
            additional_claims={
                "identity_type": "person",
            },
        )
        if is_from_browser(request.user_agent):
            response = jsonify({"refresh": True})
            set_access_cookies(response, access_token)
            unset_refresh_cookies(response)
        else:
            return {"access_token": access_token}


class RegistrationResource(Resource, ArgsMixin):
    """
    Allow a user to register himself to the service.
    """

    def post(self):
        """
        Register new user
        ---
        description: Allow a user to register himself to the service.
        tags:
            - Authentication
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  email:
                    type: string
                    format: email
                    example: admin@example.com
                    description: User email address
                  password:
                    type: string
                    format: password
                    description: User password
                  password_2:
                    type: string
                    format: password
                    description: Password confirmation
                  first_name:
                    type: string
                    description: User first name
                  last_name:
                    type: string
                    description: User last name
                required:
                  - email
                  - password
                  - password_2
                  - first_name
                  - last_name
        responses:
          201:
            description: Registration successful
          400:
            description: Invalid password or email
        """
        (
            email,
            password,
            password_2,
            first_name,
            last_name,
        ) = self.get_arguments()

        try:
            email = auth.validate_email(email)
            auth.validate_password(password, password_2)
            password = auth.encrypt_password(password)
            persons_service.create_person(
                email, password, first_name, last_name
            )
            return {"registration_success": True}, 201
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
        except auth.EmailNotValidException as exception:
            return {"error": True, "message": str(exception)}, 400

    def get_arguments(self):
        args = self.get_args(
            [
                {
                    "name": "email",
                    "required": True,
                    "help": "User email is missing.",
                },
                {
                    "name": "first_name",
                    "required": True,
                    "help": "First name is missing.",
                },
                {
                    "name": "last_name",
                    "required": True,
                    "help": "Last name is missing.",
                },
                {
                    "name": "password",
                    "required": True,
                    "help": "Password is missing.",
                },
                {
                    "name": "password_2",
                    "required": True,
                    "help": "Confirmation password is missing.",
                },
            ]
        )

        return (
            args["email"],
            args["password"],
            args["password_2"],
            args["first_name"],
            args["last_name"],
        )


class ChangePasswordResource(Resource, ArgsMixin):

    @jwt_required()
    @permissions.require_person
    def post(self):
        """
        Change user password
        ---
        description: Allow the user to change his password. Requires current
          password for verification and password confirmation to ensure
          accuracy.
        tags:
            - Authentication
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  old_password:
                    type: string
                    format: password
                    description: Current password
                  password:
                    type: string
                    format: password
                    description: New password
                  password_2:
                    type: string
                    format: password
                    description: New password confirmation
                required:
                  - old_password
                  - password
                  - password_2
        responses:
          200:
            description: Password changed
          400:
            description: Invalid password or inactive user
        """
        (old_password, password, password_2) = self.get_arguments()

        try:
            user = persons_service.get_current_user()
            auth_service.check_auth(
                app, user["email"], old_password, no_otp=True
            )
            auth.validate_password(password, password_2)
            password = auth.encrypt_password(password)
            persons_service.update_password(user["email"], password)
            current_app.logger.info(
                "User %s has changed his password" % user["email"]
            )
            organisation = persons_service.get_organisation()
            time_string = format_datetime(
                date_helpers.get_utc_now_datetime(),
                tzinfo=user["timezone"],
                locale=user["locale"],
            )
            person_IP = request.headers.get("X-Forwarded-For", None)
            html = f"""<p>Hello {user["first_name"]},</p>

<p>
You have successfully changed your password at this date: {time_string}.
</p>
<p>
Your IP when you have changed your password is: {person_IP}.
</p>
"""
            subject = f"{organisation['name']} - Kitsu: password changed"
            title = "Password Changed"
            email_html_body = templates_service.generate_html_body(title, html)
            emails.send_email(subject, email_html_body, user["email"])
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
        except UnactiveUserException:
            return {"error": True, "message": "User is unactive."}, 400
        except WrongPasswordException:
            return {"error": True, "message": "Old password is wrong."}, 400

    def get_arguments(self):
        args = self.get_args(
            [
                {
                    "name": "old_password",
                    "required": True,
                    "help": "Old password is missing.",
                },
                {
                    "name": "password",
                    "required": True,
                    "help": "New password is missing.",
                },
                {
                    "name": "password_2",
                    "required": True,
                    "help": "New password confirmation is missing.",
                },
            ]
        )

        return (args["old_password"], args["password"], args["password_2"])


class ResetPasswordResource(Resource, ArgsMixin):

    def put(self):
        """
        Reset password with token
        ---
        description: Allow a user to change his password when he forgets it.
          It uses a token sent by email to the user to verify it is the user
          who requested the password reset.
        tags:
            - Authentication
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  email:
                    type: string
                    format: email
                    example: admin@example.com
                    description: User email address
                  token:
                    type: string
                    format: JWT token
                    description: Password reset token
                  password:
                    type: string
                    format: password
                    description: New password
                  password2:
                    type: string
                    format: password
                    description: New password confirmation
                required:
                  - email
                  - token
                  - password
                  - password2
        responses:
          200:
            description: Password reset
          400:
            description: Invalid password
                         Wrong or expired token
                         Inactive user
        """
        args = self.get_args(
            [
                ("email", "", True),
                ("token", "", True),
                ("password", "", True),
                ("password2", "", True),
            ]
        )

        try:
            token_from_store = auth_tokens_store.get(
                "reset-token-%s" % args["email"]
            )
            if token_from_store == args["token"]:
                auth.validate_password(args["password"], args["password2"])
                password = auth.encrypt_password(args["password"])
                persons_service.update_password(args["email"], password)
                auth_tokens_store.delete("reset-token-%s" % args["email"])
                current_app.logger.info(
                    "User %s has reset his password" % args["email"]
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
        except UnactiveUserException:
            return {"error": True, "message": "User is inactive."}, 400

    def post(self):
        """
        Request password reset
        ---
        description: Send a password reset token by email to the user.
          It uses a classic scheme where a token is sent by email.
        tags:
            - Authentication
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  email:
                    type: string
                    format: email
                    example: admin@example.com
                    description: User email address
                required:
                  - email
        responses:
          200:
            description: Reset token sent
          400:
            description: Email not listed in database
        """
        args = self.get_args([("email", "", True)])

        try:
            user = persons_service.get_person_by_email(args["email"])
            if not user["active"]:
                return (
                    {"error": True, "message": "This user is inactive."},
                    400,
                )
        except PersonNotFoundException:
            return (
                {"error": True, "message": "Email not listed in database."},
                400,
            )

        token = auth_service.generate_reset_token()
        auth_tokens_store.add(
            "reset-token-%s" % args["email"], token, ttl=3600 * 2
        )
        params = {"email": args["email"], "token": token}
        query = urllib.parse.urlencode(params)
        reset_url = "%s://%s/reset-change-password?%s" % (
            config.DOMAIN_PROTOCOL,
            config.DOMAIN_NAME,
            query,
        )
        time_string = format_datetime(
            date_helpers.get_utc_now_datetime(),
            tzinfo=user["timezone"],
            locale=user["locale"],
        )
        person_IP = request.headers.get("X-Forwarded-For", None)
        organisation = persons_service.get_organisation()
        html = f"""<p>Hello {user["first_name"]},</p>

<p>
You have requested for a password reset. Click on the following button
to change your password:
</p>

<p class="cta">
<a class="button" href="{reset_url}">Change your password</a>
</p>

<p>
This link will expire after 2 hours. After, you have to do a new request to reset your password.
This email was sent at this date: {time_string}.
The IP of the person who requested this is: {person_IP}.
</p>
"""
        subject = f"{organisation['name']} - Kitsu: password recovery"
        title = "Password Recovery"
        email_html_body = templates_service.generate_html_body(title, html)
        emails.send_email(subject, email_html_body, args["email"])
        return {"success": "Reset token sent"}


class TOTPResource(Resource, ArgsMixin):

    @jwt_required()
    @permissions.require_person
    def put(self):
        """
        Pre-enable TOTP
        ---
        description: Prepare TOTP (Time-based One-Time Password) for enabling.
          It returns provisioning URI and secret for authenticator app setup.
        tags:
            - Authentication
        responses:
          200:
            description: TOTP pre-enabled
          400:
            description: TOTP already enabled
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
    def post(self):
        """
        Enable TOTP
        ---
        description: Enable TOTP (Time-based One-Time Password) authentication.
          It requires verification code from authenticator app.
        tags:
            - Authentication
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  totp:
                    type: string
                    description: TOTP verification code from authenticator app
                required:
                  - totp
        responses:
          200:
            description: TOTP enabled
          400:
            description: TOTP already enabled or verification failed
        """
        args = self.get_args([("totp", "", True)])

        try:
            otp_recovery_codes = auth_service.enable_totp(
                persons_service.get_current_user()["id"], args["totp"]
            )
            return {"otp_recovery_codes": otp_recovery_codes}
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
    def delete(self):
        """
        Disable TOTP
        ---
        description: Disable TOTP (Time-based One-Time Password) authentication.
          It requires two-factor authentication verification.
        tags:
            - Authentication
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  totp:
                    type: string
                    description: TOTP verification code
                  email_otp:
                    type: string
                    description: Email OTP verification code
                  fido_authentication_response:
                    type: object
                    description: FIDO authentication response
                  recovery_code:
                    type: string
                    description: Recovery code for two-factor authentication
        responses:
          200:
            description: TOTP disabled
          400:
            description: TOTP not enabled or verification failed
        """
        args = self.get_args(
            [
                ("totp", None, False),
                ("email_otp", None, False),
                ("fido_authentication_response", {}, False, dict),
                ("recovery_code", None, False),
            ]
        )

        try:
            person = persons_service.get_current_user(unsafe=True)
            if not auth_service.person_two_factor_authentication_enabled(
                person
            ):
                raise TOTPNotEnabledException
            if not auth_service.check_two_factor_authentication(
                person,
                args["totp"],
                args["email_otp"],
                args["fido_authentication_response"],
                args["recovery_code"],
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


class EmailOTPResource(Resource, ArgsMixin):

    def get(self):
        """
        Send email OTP
        ---
        description: Send a one-time password by email to the user for
          authentication.
        tags:
            - Authentication
        parameters:
          - in: query
            name: email
            required: True
            type: string
            format: email
            description: User email address
        responses:
          200:
            description: OTP by email sent
          400:
            description: OTP by email not enabled
        """
        args = self.get_args(
            [
                ("email", None, True),
            ],
            location="values",
        )

        try:
            try:
                person = persons_service.get_person_by_email_desktop_login(
                    args["email"]
                )
            except PersonNotFoundException:
                raise WrongUserException()
            if not person["email_otp_enabled"]:
                raise EmailOTPNotEnabledException
            auth_service.send_email_otp(person)
            return {"success": True}
        except EmailOTPNotEnabledException:
            return (
                {"error": True, "message": "OTP by email not enabled."},
                400,
            )
        except WrongUserException:
            return (
                {"error": True, "message": "User not found."},
                404,
            )

    @jwt_required()
    @permissions.require_person
    def put(self):
        """
        Pre-enable email OTP
        ---
        description: Prepare email OTP (One-Time Password) for enabling.
          It sets up email-based two-factor authentication.
        tags:
            - Authentication
        responses:
          200:
            description: Email OTP pre-enabled
          400:
            description: Email OTP already enabled
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
    def post(self):
        """
        Enable email OTP
        ---
        description: Enable email OTP (One-Time Password) authentication.
          It requires verification code sent to email.
        tags:
            - Authentication
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  email_otp:
                    type: string
                    description: Email OTP verification code
                required:
                  - email_otp
        responses:
          200:
            description: Email OTP enabled
          400:
            description: Email OTP already enabled or verification failed
        """
        args = self.get_args([("email_otp", "", True)])

        try:
            otp_recovery_codes = auth_service.enable_email_otp(
                persons_service.get_current_user()["id"],
                args["email_otp"],
            )
            return {"otp_recovery_codes": otp_recovery_codes}
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
    def delete(self):
        """
        Disable email OTP
        ---
        description: Disable email OTP (One-Time Password) authentication.
          It requires two-factor authentication verification.
        tags:
            - Authentication
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  totp:
                    type: string
                    description: TOTP verification code
                  email_otp:
                    type: string
                    description: Email OTP verification code
                  fido_authentication_response:
                    type: object
                    description: FIDO authentication response
                  recovery_code:
                    type: string
                    description: Recovery code for two-factor authentication
        responses:
          200:
            description: Email OTP disabled
          400:
            description: Email OTP not enabled or verification failed
        """
        args = self.get_args(
            [
                ("totp", None, False),
                ("email_otp", None, False),
                ("fido_authentication_response", {}, False, dict),
                ("recovery_code", None, False),
            ]
        )

        try:
            person = persons_service.get_current_user(unsafe=True)
            if not auth_service.person_two_factor_authentication_enabled(
                person
            ):
                raise EmailOTPNotEnabledException
            if not auth_service.check_two_factor_authentication(
                person,
                args["totp"],
                args["email_otp"],
                args["fido_authentication_response"],
                args["recovery_code"],
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


class FIDOResource(Resource, ArgsMixin):
    """
    Resource to allow a user to register/unregister FIDO device or to get a
    challenge for a FIDO device.
    """

    def get(self):
        """
        Get FIDO challenge
        ---
        description: Get a challenge for FIDO device authentication.
          It is used for WebAuthn authentication flow.
        tags:
            - Authentication
        parameters:
          - in: query
            name: email
            required: True
            type: string
            format: email
            description: User email address
        responses:
          200:
            description: FIDO challenge generated
          400:
            description: FIDO not enabled
        """
        args = self.get_args(
            [
                ("email", None, True),
            ],
            location="values",
        )

        try:
            try:
                person = persons_service.get_person_by_email_desktop_login(
                    args["email"]
                )
            except PersonNotFoundException:
                raise WrongUserException()
            if not person["fido_enabled"]:
                raise FIDONotEnabledException
            return auth_service.get_challenge_fido(person["id"])
        except FIDONotEnabledException:
            return (
                {"error": True, "message": "FIDO not enabled."},
                400,
            )
        except WrongUserException:
            return (
                {"error": True, "message": "User not found."},
                404,
            )

    @jwt_required()
    @permissions.require_person
    def put(self):
        """
        Pre-register FIDO device
        ---
        description: Prepare FIDO device for registration.
          It returns registration options for WebAuthn.
        tags:
            - Authentication
        responses:
          200:
            description: FIDO device pre-registered data
          400:
            description: Invalid request
        """
        return auth_service.pre_register_fido(
            persons_service.get_current_user()["id"]
        )

    @permissions.require_person
    @jwt_required()
    def post(self):
        """
        Register FIDO device
        ---
        description: Register a FIDO device for WebAuthn authentication.
          It requires registration response from the device.
        tags:
            - Authentication
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  registration_response:
                    type: object
                    description: FIDO device registration response
                  device_name:
                    type: string
                    description: Name for the FIDO device
                required:
                  - registration_response
                  - device_name
        responses:
          200:
            description: FIDO device registered
          400:
            description: Registration failed or no preregistration
        """
        try:
            args = self.get_args(
                [
                    ("registration_response", {}, True, dict),
                    ("device_name", "", True),
                ]
            )

            otp_recovery_codes = auth_service.register_fido(
                persons_service.get_current_user()["id"],
                args["registration_response"],
                args["device_name"],
            )
            return {"otp_recovery_codes": otp_recovery_codes}
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
    def delete(self):
        """
        Unregister FIDO device
        ---
        description: Unregister a FIDO device from WebAuthn authentication.
          It requires two-factor authentication verification.
        tags:
            - Authentication
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  totp:
                    type: string
                    description: TOTP verification code
                  email_otp:
                    type: string
                    description: Email OTP verification code
                  fido_authentication_response:
                    type: object
                    description: FIDO authentication response
                  recovery_code:
                    type: string
                    description: Recovery code for two-factor authentication
                  device_name:
                    type: string
                    description: Name of the FIDO device to unregister
                required:
                  - device_name
        responses:
          200:
            description: FIDO device unregistered
          400:
            description: FIDO not enabled or verification failed
        """
        args = self.get_args(
            [
                ("totp", None, False),
                ("email_otp", None, False),
                ("fido_authentication_response", {}, False, dict),
                ("recovery_code", None, False),
                ("device_name", None, True),
            ]
        )

        try:
            person = persons_service.get_current_user(unsafe=True)
            if not auth_service.person_two_factor_authentication_enabled(
                person
            ):
                raise FIDONotEnabledException
            if not auth_service.check_two_factor_authentication(
                person,
                args["totp"],
                args["email_otp"],
                args["fido_authentication_response"],
                args["recovery_code"],
            ):
                raise WrongOTPException
            auth_service.unregister_fido(person["id"], args["device_name"])
            return {"success": True}
        except FIDONotEnabledException:
            return (
                {"error": True, "message": "FIDO not enabled."},
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


class RecoveryCodesResource(Resource, ArgsMixin):

    @jwt_required()
    @permissions.require_person
    def put(self):
        """
        Generate recovery codes
        ---
        description: Generate new recovery codes for two-factor authentication.
          It requires two-factor authentication verification.
        tags:
            - Authentication
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  totp:
                    type: string
                    description: TOTP verification code
                  email_otp:
                    type: string
                    description: Email OTP verification code
                  fido_authentication_response:
                    type: object
                    description: FIDO authentication response
                  recovery_code:
                    type: string
                    description: Recovery code for two-factor authentication
        responses:
          200:
            description: New recovery codes generated
          400:
            description: No two-factor authentication enabled or verification failed
        """
        args = self.get_args(
            [
                ("totp", None, False),
                ("email_otp", None, False),
                ("fido_authentication_response", {}, False, dict),
                ("recovery_code", None, False),
            ]
        )

        try:
            person = persons_service.get_current_user(unsafe=True)
            if not auth_service.person_two_factor_authentication_enabled(
                person
            ):
                raise NoTwoFactorAuthenticationEnabled
            if not auth_service.check_two_factor_authentication(
                person,
                args["totp"],
                args["email_otp"],
                args["fido_authentication_response"],
                args["recovery_code"],
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


class SAMLSSOResource(Resource, ArgsMixin):
    def post(self):
        """
        SAML SSO login
        ---
        description: Handle SAML SSO login response. Processes authentication
          response from SAML identity provider and creates a new user if they
          don't exist.
        tags:
            - Authentication
        responses:
          302:
            description: Login successful, redirect to home page
          400:
            description: SAML not enabled or wrong parameter
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
                if isinstance(v, list) and k in ["first_name", "last_name"]
                else v
            )
            for k, v in authn_response.ava.items()
            if k
            in [
                "first_name",
                "last_name",
                "phone",
                "role",
                "departments",
                "studio_id",
                "active",
            ]
        }
        try:
            user = persons_service.get_person_by_email(email)
            for k, v in person_info.items():
                if user.get(k) != v:
                    persons_service.update_person(
                        user["id"], person_info, bypass_protected_accounts=True
                    )
                    break
        except PersonNotFoundException:
            user = persons_service.create_person(
                email, "default".encode("utf-8"), **person_info
            )

        response = make_response(
            redirect(f"{config.DOMAIN_PROTOCOL}://{config.DOMAIN_NAME}")
        )

        if user["active"]:
            access_token = create_access_token(
                identity=user["id"],
                additional_claims={
                    "identity_type": "person",
                },
            )
            refresh_token = create_refresh_token(
                identity=user["id"],
                additional_claims={
                    "identity_type": "person",
                },
            )
            identity_changed.send(
                current_app._get_current_object(),
                identity=Identity(user["id"], "person"),
            )

            ip_address = request.environ.get(
                "HTTP_X_REAL_IP", request.remote_addr
            )

            set_access_cookies(response, access_token)
            set_refresh_cookies(response, refresh_token)
            events_service.create_login_log(user["id"], ip_address, "web")

        return response


class SAMLLoginResource(Resource, ArgsMixin):

    def get(self):
        """
        SAML SSO login redirect
        ---
        description: Initiate SAML SSO login by redirecting to SAML identity
          provider.
        tags:
            - Authentication
        responses:
          302:
            description: Redirect to SAML identity provider
          400:
            description: SAML not enabled or wrong parameter
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
