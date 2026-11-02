"""Unit tests for password hashing and access-token validation."""

from datetime import timedelta

import pytest
from jose import JWTError

from app.core.security import create_access_token, decode_access_token, hash_password, verify_password


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
