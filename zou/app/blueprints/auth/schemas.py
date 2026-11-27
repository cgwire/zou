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
    Body to change the password of the user.
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
    Body to reset the password with a token.
    """

    email: str = Field(..., min_length=1)
    token: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    password2: str = Field(..., min_length=1)


class ResetPasswordCheckSchema(BaseSchema):
    """
    Body to check a password reset token.
    """

    email: str = Field(..., min_length=1)
    token: str = Field(..., min_length=1)


class SendPasswordResetSchema(BaseSchema):
    """
    Body to ask for a password reset email.
    """

    email: str = Field(..., min_length=1)


class TwoFactorAuthSchema(BaseSchema):
    """
    Body to verify a two-factor authentication.
    """

    totp: Optional[str] = None
    email_otp: Optional[str] = None
    fido_authentication_response: Optional[dict] = None
    recovery_code: Optional[str] = None


class TotpSchema(TwoFactorAuthSchema):
    """
    Body to enable TOTP. The inherited fields carry a factor that is
    already enabled. The endpoint asks for it if the account has one.
    """

    totp: str = Field(..., min_length=1, description="TOTP verification code")


class EmailOtpSchema(TwoFactorAuthSchema):
    """
    Body to enable email OTP. The inherited fields carry a factor that is
    already enabled. The endpoint asks for it if the account has one.
    """

    email_otp: str = Field(
        ..., min_length=1, description="Email OTP verification code"
    )


class FidoRegisterSchema(TwoFactorAuthSchema):
    """
    Body to register a FIDO device. The inherited fields carry a factor
    that is already enabled. The endpoint asks for it if the account has
    one.
    """

    registration_response: dict = Field(
        ..., description="FIDO device registration response"
    )
    device_name: str = Field(
        ..., min_length=1, description="Name for the FIDO device"
    )


class FidoUnregisterSchema(BaseSchema):
    """
    Body to unregister a FIDO device.
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
    Body fields that prove again the identity of the caller, before a
    change that a session alone must not allow. They are the current
    password, and a second factor if one is enabled.
    """

    current_password: str = Field(
        ..., min_length=1, description="Current password"
    )


class AppLoginCodeSchema(BaseSchema):
    """
    Body to create a browser login code for a desktop app or a script.
    """

    code_challenge: str = Field(
        ...,
        pattern=r"^[A-Za-z0-9_-]{43}$",
        description="Base64url SHA-256 of the PKCE code verifier",
    )


class AppLoginTokenSchema(BaseSchema):
    """
    Body to exchange a browser login code for a token pair.
    """

    code: str = Field(
        ..., min_length=1, max_length=128, description="One-time login code"
    )
    code_verifier: str = Field(
        ...,
        pattern=r"^[A-Za-z0-9._~-]{43,128}$",
        description="PKCE code verifier",
    )
