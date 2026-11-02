"""Password hashing and signed access-token helpers."""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from jose import jwt
from pwdlib import PasswordHash

from app.core.config import settings

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Hash a password with the recommended Argon2 configuration."""
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a password against its stored hash."""
    return password_hash.verify(password, hashed_password)


def create_access_token(subject: str, expires_delta: timedelta | None = None, token_version: int = 0) -> tuple[str, str, datetime]:
    """Create an access token and return its JWT ID and expiry for revocation."""
    expires = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    token_id = str(uuid4())
    token = jwt.encode(
        {"sub": subject, "jti": token_id, "type": "access", "ver": token_version, "iat": datetime.now(timezone.utc), "exp": expires},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return token, token_id, expires


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode a token using the configured algorithm and signing key."""
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
