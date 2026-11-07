"""Unit tests for password hashing and access-token validation."""

from datetime import timedelta

import pytest
from jose import JWTError

from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.schemas.auth import Credentials, PasswordResetRequest, RegistrationRequest
from pydantic import ValidationError


def test_password_hash_is_not_plaintext_and_verifies() -> None:
    """Passwords are stored as hashes and can be checked."""
    password = "correct horse battery staple"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("incorrect password", hashed)


def test_access_token_has_revocation_claims() -> None:
    """Issued tokens include a unique ID and access-token type."""
    token, token_id, _expiry = create_access_token("42")
    claims = decode_access_token(token)
    assert claims["sub"] == "42"
    assert claims["jti"] == token_id
    assert claims["type"] == "access"


def test_expired_access_token_is_rejected() -> None:
    """Expired tokens cannot be decoded as valid access tokens."""
    token, _token_id, _expiry = create_access_token("42", timedelta(seconds=-1))
    with pytest.raises(JWTError):
        decode_access_token(token)


def test_new_account_password_policy_requires_all_character_groups() -> None:
    base = {
        "email": "policy@example.com",
        "password": "GoodPassword1!",
        "confirm_password": "GoodPassword1!",
        "full_name": "Policy User",
        "username": "policy_user",
    }
    RegistrationRequest(**base)
    for weak_password in ("alllowercase1!", "ALLUPPERCASE1!", "NoDigitsHere!!", "NoSpecialChar123", "Short1!"):
        with pytest.raises(ValidationError):
            RegistrationRequest(**{**base, "password": weak_password, "confirm_password": weak_password})


def test_password_reset_uses_same_policy() -> None:
    PasswordResetRequest(authorization_token="x" * 32, password="GoodPassword1!", confirm_password="GoodPassword1!")
    with pytest.raises(ValidationError, match="uppercase letter"):
        PasswordResetRequest(authorization_token="x" * 32, password="goodpassword1!", confirm_password="goodpassword1!")


def test_login_schema_accepts_legacy_passwords_below_new_creation_policy() -> None:
    # Authentication must not prevent existing accounts from signing in.
    credentials = Credentials(email="legacy@example.com", password="OldPass1!")
    assert credentials.password.get_secret_value() == "OldPass1!"
