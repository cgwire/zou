from flask import Blueprint

from zou.app.blueprints.auth.resources import (
    AppLoginCodeResource,
    AppLoginTokenResource,
    AuthenticatedResource,
    ChangePasswordResource,
    EmailOTPResource,
    FIDOResource,
    LoginResource,
    LogoutResource,
    OIDCCallbackResource,
    OIDCLoginResource,
    RecoveryCodesResource,
    RefreshTokenResource,
    ResetPasswordResource,
    SAMLLoginResource,
    SAMLSSOResource,
    TOTPResource,
)
from zou.app.utils.api import configure_api_from_blueprint

routes = [
    ("/auth/login", LoginResource),
    ("/auth/logout", LogoutResource),
    ("/auth/authenticated", AuthenticatedResource),
    ("/auth/change-password", ChangePasswordResource),
    ("/auth/reset-password", ResetPasswordResource),
    ("/auth/refresh-token", RefreshTokenResource),
    ("/auth/app-login/code", AppLoginCodeResource),
    ("/auth/app-login/token", AppLoginTokenResource),
    ("/auth/totp", TOTPResource),
    ("/auth/email-otp", EmailOTPResource),
    ("/auth/recovery-codes", RecoveryCodesResource),
    ("/auth/fido", FIDOResource),
    ("/auth/saml/sso", SAMLSSOResource),
    ("/auth/saml/login", SAMLLoginResource),
    ("/auth/oidc/login", OIDCLoginResource),
    ("/auth/oidc/callback", OIDCCallbackResource),
]

blueprint = Blueprint("auth", "auth")
api = configure_api_from_blueprint(blueprint, routes)
