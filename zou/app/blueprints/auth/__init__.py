from flask import Blueprint
from zou.app.utils.api import configure_api_from_blueprint

from zou.app.blueprints.auth.resources import (
    AuthenticatedResource,
    ChangePasswordResource,
    EmailOTPResource,
    FIDOResource,
    LoginResource,
    LogoutResource,
    RecoveryCodesResource,
    RefreshTokenResource,
    RegistrationResource,
    ResetPasswordResource,
    TOTPResource,
)

routes = [
    ("/auth/login", LoginResource),
    ("/auth/logout", LogoutResource),
    ("/auth/authenticated", AuthenticatedResource),
    ("/auth/register", RegistrationResource),
    ("/auth/change-password", ChangePasswordResource),
    ("/auth/reset-password", ResetPasswordResource),
    ("/auth/refresh-token", RefreshTokenResource),
    ("/auth/totp", TOTPResource),
    ("/auth/email-otp", EmailOTPResource),
    ("/auth/recovery-codes", RecoveryCodesResource),
    ("/auth/fido", FIDOResource),
]

blueprint = Blueprint("auth", "auth")
api = configure_api_from_blueprint(blueprint, routes)
