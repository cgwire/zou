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
    get_jwt,
)

from sqlalchemy.exc import OperationalError, TimeoutError
from babel.dates import format_datetime
from saml2 import entity

from zou.app import app, config
from zou.app.mixin import ArgsMixin
from zou.app.utils import auth, emails, permissions, date_helpers
from zou.app.services import (
    persons_service,
    auth_service,
    events_service,
)

from zou.app.utils.flask import is_from_browser

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
    """
    Returns information if the user is authenticated else it returns a 401
    response.
    It can be used by third party tools, especially browser frontend, to know
    if current user is still logged in.
    """

    @jwt_required()
    def get(self):
        """
        Returns information if the user is authenticated else it returns a 401
        response.
        ---
        description:  It can be used by third party tools, especially browser frontend, to know if current user is still logged in.
        tags:
            - Authentication
        responses:
          200:
            description: User authenticated
          401:
            description: Person not found
        """
        person = persons_service.get_current_user(relations=True)
        organisation = persons_service.get_organisation()
        return {
            "authenticated": True,
            "user": person,
            "organisation": organisation,
        }


class LogoutResource(Resource):
    """
    Log user out by revoking his auth tokens. Once log out, current user
    cannot access to API anymore.
    """

    @jwt_required()
    @permissions.require_person
    def get(self):
        """
        Log user out by revoking his auth tokens.
        ---
        description: Once logged out, current user cannot access the API anymore.
        tags:
            - Authentication
        responses:
          200:
            description: Logout successful
          500:
            description: Access token not found
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
    """
    Log in user by creating and registering auth tokens. Login is based
    on email and password. If no user match given email and a destkop ID,
    it looks in matching the desktop ID with the one stored in database. It is
    useful for clients that run on desktop tools and that don't know user
    email.
    """

    def post(self):
        """
        Log in user by creating and registering auth tokens.
        ---
        description: Login is based on email and password.
                     If no user match given email and a destkop ID, it looks in matching the desktop ID with the one stored in database.
                     It is useful for clients that run on desktop tools and that don't know user email.
        tags:
            - Authentication
        parameters:
          - in: formData
            name: email
            required: True
            type: string
            format: email
            x-example: admin@example.com
          - in: formData
            name: password
            required: True
            type: string
            format: password
            x-example: mysecretpassword
          - in: formData
            name: otp
            required: False
            type: string
            format: password
            x-example: 123456
        responses:
          200:
            description: Login successful
          400:
            description: Login failed
          500:
            description: Database not reachable
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

            if is_from_browser(request.user_agent):
                organisation = persons_service.get_organisation()
                response = jsonify(
                    {
                        "user": user,
                        "organisation": organisation,
                        "login": True,
                    }
                )
                set_access_cookies(response, access_token)
                set_refresh_cookies(response, refresh_token)
                events_service.create_login_log(user["id"], ip_address, "web")
            else:
                events_service.create_login_log(
                    user["id"], ip_address, "script"
                )
                response = {
                    "login": True,
                    "user": user,
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                }
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
        Tokens are considered as outdated every two weeks.
        ---
        description: This route allows to make their lifetime long before they get outdated.
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
        else:
            return {"access_token": access_token}


class RegistrationResource(Resource, ArgsMixin):
    """
    Allow a user to register himself to the service.
    """

    def post(self):
        """
        Allow a user to register himself to the service.
        ---
        tags:
            - Authentication
        parameters:
          - in: formData
            name: email
            required: True
            type: string
            format: email
            x-example: admin@example.com
          - in: formData
            name: password
            required: True
            type: string
            format: password
          - in: formData
            name: password_2
            required: True
            type: string
            format: password
          - in: formData
            name: first_name
            required: True
            type: string
          - in: formData
            name: last_name
            required: True
            type: string
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
    """
    Allow the user to change his password. Prior to modify the password,
    it requires to give the current password (to make sure the user changing
    the password is not someone who stealed the session).
    The new password requires a confirmation to ensure that the user didn't
    make mistake by typing his new password.
    """

    @jwt_required()
    @permissions.require_person
    def post(self):
        """
        Allow the user to change his password.
        ---
        description: Prior to modifying the password, it requires to give the current password
                     (to make sure the user changing the password is not someone who stealed the session).
                     The new password requires a confirmation to ensure that the user didn't
                     make a mistake by typing his new password.
        tags:
            - Authentication
        parameters:
          - in: formData
            name: old_password
            required: True
            type: string
            format: password
          - in: formData
            name: password
            required: True
            type: string
            format: password
          - in: formData
            name: password_2
            required: True
            type: string
            format: password
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
You have successfully changed your password at this date : {time_string}.

Your IP when you have changed your password is : {person_IP}.
</p>

Thank you and see you soon on Kitsu,
</p>
<p>
{organisation["name"]} Team
</p>
"""
            subject = f"{organisation['name']} - Kitsu: password changed"
            emails.send_email(subject, html, user["email"])
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
    """
    Resource to allow a user to change his password when he forgets it.
    It uses a classic scheme: a token is sent by email to the user. Then
    he can change his password.
    """

    def put(self):
        """
        Resource to allow a user to change his password when he forgets it.
        ---
        description: "It uses a classic scheme: a token is sent by email to the user.
                     Then he can change his password."
        tags:
            - Authentication
        parameters:
          - in: formData
            name: email
            required: True
            type: string
            format: email
            x-example: admin@example.com
          - in: formData
            name: token
            required: True
            type: string
            format: JWT token
          - in: formData
            name: password
            required: True
            type: string
            format: password
          - in: formData
            name: password2
            required: True
            type: string
            format: password
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
        Resource to allow a user to change his password when he forgets it.
        ---
        description: "It uses a classic scheme: a token is sent by email to the user.
                     Then he can change his password."
        tags:
            - Authentication
        parameters:
          - in: formData
            name: email
            required: True
            type: string
            format: email
            x-example: admin@example.com
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
You have requested for a password reset. You can follow this link to change your
password: <a href="{reset_url}">{reset_url}</a>
</p>

<p>
This link will expire after 2 hours. After, you have to do a new request to reset your password.
This email was sent at this date: {time_string}.
The IP of the person who requested this is: {person_IP}.
</p>

Thank you and see you soon on Kitsu,
</p>
<p>
{organisation["name"]} Team
</p>
"""
        subject = f"{organisation['name']} - Kitsu: password recovery"
        emails.send_email(subject, html, args["email"])
        return {"success": "Reset token sent"}


class TOTPResource(Resource, ArgsMixin):
    """
    Resource to allow a user to enable/disable TOTP.
    """

    @jwt_required()
    @permissions.require_person
    def put(self):
        """
        Resource to allow a user to pre-enable TOTP.
        ---
        description: ""
        tags:
            - Authentication
        responses:
          200:
            description: TOTP enabled
          400:
            description: Invalid password
                         Wrong or expired token
                         Inactive user
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
        Resource to allow a user to enable TOTP.
        ---
        description: ""
        tags:
            - Authentication
        responses:
          200:
            description: TOTP enabled
          400:
            description: Invalid password
                         Wrong or expired token
                         Inactive user
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
        Resource to allow a user to disable TOTP.
        ---
        description: ""
        tags:
            - Authentication
        responses:
          200:
            description: TOTP disabled
          400:
            description: TOTP not enabled
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
    """
    Resource to allow a user to enable/disable OTP by email or to send an OTP
    by email.
    """

    def get(self):
        """
        Resource to send an OTP by email to user.
        ---
        description: ""
        tags:
            - Authentication
        responses:
          200:
            description: OTP by email sent
          400:
            description: Invalid password
                         Wrong or expired token
                         Inactive user
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
        Resource to allow a user to pre-enable OTP by email.
        ---
        description: ""
        tags:
            - Authentication
        responses:
          200:
            description: OTP by email enabled
          400:
            description: Invalid password
                         Wrong or expired token
                         Inactive user
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
        Resource to allow a user to enable OTP by email.
        ---
        description: ""
        tags:
            - Authentication
        responses:
          200:
            description: OTP by email enabled
          400:
            description: Invalid password
                         Wrong or expired token
                         Inactive user
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
        Resource to allow a user to disable OTP by email.
        ---
        description: ""
        tags:
            - Authentication
        responses:
          200:
            description: OTP by email disabled.
          400:
            description: Invalid password.
                         Wrong or expired token.
                         Inactive user.
                         Wrong 2FA.
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
        Resource to get a challenge for a FIDO device.
        ---
        description: ""
        tags:
            - Authentication
        responses:
          200:
            description: Challenge for FIDO device.
          400:
            description: Wrong parameter.
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
        Resource to allow a user to pre-register a FIDO device.
        ---
        description: ""
        tags:
            - Authentication
        responses:
          200:
            description: FIDO device pre-registered.
          400:
            description: Invalid password
                         Wrong or expired token
                         Inactive user
        """
        return auth_service.pre_register_fido(
            persons_service.get_current_user()["id"]
        )

    @permissions.require_person
    @jwt_required()
    def post(self):
        """
        Resource to allow a user to register a FIDO device.
        ---
        description: ""
        tags:
            - Authentication
        responses:
          200:
            description: FIDO device registered.
          400:
            description: Invalid password
                         Wrong or expired token
                         Inactive user
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
        Resource to allow a user to unregister a FIDO device.
        ---
        description: ""
        tags:
            - Authentication
        responses:
          200:
            description: FIDO device unregistered.
          400:
            description: Invalid password
                         Wrong or expired token
                         Inactive user
                         Wrong 2FA
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
    """
    Resource to allow a user to generate new recovery codes.
    """

    @jwt_required()
    @permissions.require_person
    def put(self):
        """
        Resource to allow a user to generate new recovery codes.
        ---
        description: ""
        tags:
            - Authentication
        responses:
          200:
            description: new recovery codes.
          400:
            description: Invalid password
                         Wrong or expired token
                         Inactive user
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
    """
    Resource to allow a user to login with SAML SSO.
    """

    def post(self):
        """
        Resource to allow a user to login with SAML SSO.
        ---
        description: ""
        tags:
            - Authentication
        responses:
          302:
            description: Login successful, redirect to the home page.
          400:
            description: Wrong parameter
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
            k: v if not isinstance(v, list) else " ".join(v)
            for k, v in authn_response.ava.items()
        }
        try:
            user = persons_service.get_person_by_email(email)
            for k, v in person_info.items():
                if user.get(k) != v:
                    persons_service.update_person(user["id"], person_info)
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
    """
    Resource to allow a user to login with SAML SSO.
    """

    def get(self):
        """
        Resource to allow a user to login with SAML SSO.
        ---
        description: ""
        tags:
            - Authentication
        responses:
          302:
            description: Redirect to the SAML IDP.
          400:
            description: Wrong parameter.
        """
        if not config.SAML_ENABLED:
            return {"error": "SAML is not enabled."}, 400
        _, info = current_app.extensions[
            "saml_client"
        ].prepare_for_authenticate()

        redirect_url = None

        # Select the IdP URL to send the AuthN request to
        for key, value in info["headers"]:
            if key == "Location":
                redirect_url = value

        return redirect(redirect_url, code=302)
