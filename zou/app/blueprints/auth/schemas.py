"""
Pydantic schemas for request body validation in the auth blueprint.
"""

from typing import Optional

from pydantic import Field

from zou.app.utils.validation import BaseSchema


class LoginSchema(BaseSchema):
    """
    Body for user login.
    """

    email: str = Field(..., min_length=1, description="User email")
    password: str = Field("default", description="User password")
    totp: Optional[str] = None
    email_otp: Optional[str] = None
    fido_authentication_response: Optional[dict] = None
    recovery_code: Optional[str] = None


class ChangePasswordSchema(BaseSchema):
    """
    Body for changing user password.
    """

    old_password: str = Field(
        ..., min_length=1, description="Current password"
    )
    password: str = Field(..., min_length=1, description="New password")
    password_2: str = Field(
        ..., min_length=1, description="New password confirmation"
    )


class ResetPasswordSchema(BaseSchema):
    """
    Body for resetting password with token.
    """

    email: str = Field(..., min_length=1)
    token: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    password2: str = Field(..., min_length=1)


class SendPasswordResetSchema(BaseSchema):
    """
    Body for requesting a password reset email.
    """

    email: str = Field(..., min_length=1)


class TwoFactorAuthSchema(BaseSchema):
    """
    Body for two-factor authentication verification.
    """

    totp: Optional[str] = None
    email_otp: Optional[str] = None
    fido_authentication_response: Optional[dict] = None
    recovery_code: Optional[str] = None


class TotpSchema(TwoFactorAuthSchema):
    """
    Body for enabling TOTP. The inherited fields carry a factor already
    enabled, asked for when the account has one.
    """

    totp: str = Field(..., min_length=1, description="TOTP verification code")


class EmailOtpSchema(TwoFactorAuthSchema):
    """
    Body for enabling email OTP. The inherited fields carry a factor already
    enabled, asked for when the account has one.
    """

    email_otp: str = Field(
        ..., min_length=1, description="Email OTP verification code"
    )


class FidoRegisterSchema(TwoFactorAuthSchema):
    """
    Body for registering a FIDO device. The inherited fields carry a factor
    already enabled, asked for when the account has one.
    """

    registration_response: dict = Field(
        ..., description="FIDO device registration response"
    )
    device_name: str = Field(
        ..., min_length=1, description="Name for the FIDO device"
    )


class FidoUnregisterSchema(BaseSchema):
    """
    Body for unregistering a FIDO device.
    """

    device_name: str = Field(
        ..., min_length=1, description="Name of the FIDO device to unregister"
    )
    totp: Optional[str] = None
    email_otp: Optional[str] = None
    fido_authentication_response: Optional[dict] = None
    recovery_code: Optional[str] = None


class CurrentCredentialsSchema(TwoFactorAuthSchema):
    """
    Body fields proving again who the caller is, before a change a session
    alone must not allow: the current password, plus a second factor when
    one is enabled.
    """

    current_password: str = Field(
        ..., min_length=1, description="Current password"
    )


class AppLoginCodeSchema(BaseSchema):
    """
    Body for minting a browser login code for a desktop app or a script.
    """

    code_challenge: str = Field(
        ...,
        pattern=r"^[A-Za-z0-9_-]{43}$",
        description="Base64url SHA-256 of the PKCE code verifier",
    )


class AppLoginTokenSchema(BaseSchema):
    """
    Body for trading a browser login code for a token pair.
    """

    code: str = Field(
        ..., min_length=1, max_length=128, description="One-time login code"
    )
    code_verifier: str = Field(
        ...,
        pattern=r"^[A-Za-z0-9._~-]{43,128}$",
        description="PKCE code verifier",
    )
