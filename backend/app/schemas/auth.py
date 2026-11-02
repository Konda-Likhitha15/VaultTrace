"""Authentication request and response schemas."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, SecretStr, model_validator


class Credentials(BaseModel):
    """Email and password supplied during login."""

    email: EmailStr
    password: SecretStr = Field(min_length=12, max_length=128)


class RegistrationRequest(Credentials):
    """New account request; role assignment is never client controlled."""

    full_name: str = Field(min_length=1, max_length=160)
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    phone_number: str | None = Field(default=None, max_length=32)
    confirm_password: SecretStr = Field(min_length=12, max_length=128)

    @model_validator(mode="after")
    def passwords_match(self) -> "RegistrationRequest":
        """Reject mismatched password confirmation before persistence."""
        if self.password.get_secret_value() != self.confirm_password.get_secret_value():
            raise ValueError("Passwords do not match")
        return self


class OtpRequest(BaseModel):
    """Request an email verification code."""

    email: EmailStr


class OtpVerificationRequest(OtpRequest):
    """Submit the six-digit code delivered to an email address."""

    otp: str = Field(pattern=r"^\d{6}$")


class PasswordResetOtpVerificationRequest(OtpVerificationRequest):
    """Submit a password-reset code for single-use reset authorization."""


class PasswordResetRequest(BaseModel):
    """Exchange a verified reset authorization for a new password."""

    authorization_token: str = Field(min_length=32, max_length=256)
    password: SecretStr = Field(min_length=12, max_length=128)
    confirm_password: SecretStr = Field(min_length=12, max_length=128)

    @model_validator(mode="after")
    def passwords_match(self) -> "PasswordResetRequest":
        """Reject mismatched password confirmation."""
        if self.password.get_secret_value() != self.confirm_password.get_secret_value():
            raise ValueError("Passwords do not match")
        return self


class ResetAuthorizationResponse(BaseModel):
    """Short-lived authorization issued after a successful reset OTP."""

    authorization_token: str
    expires_in_seconds: int


class OtpResponse(BaseModel):
    """Non-sensitive OTP operation response."""

    message: str


class RegistrationResponse(BaseModel):
    """Public response after a signup application is submitted."""

    message: str
    application_id: int
    approval_status: str


class UserResponse(BaseModel):
    """Public user information without password or token data."""

    id: int
    email: EmailStr
    full_name: str
    username: str
    role: str
    account_status: str = "ACTIVE"


class TokenResponse(BaseModel):
    """Bearer token response returned by successful authentication."""

    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserResponse
