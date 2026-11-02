"""Business logic for account registration and authentication."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, verify_password
from app.models import RevokedToken, User
from app.schemas.auth import Credentials


class InvalidCredentials(Exception):
    """Raised for an unknown account or incorrect password."""


def authenticate_user(db: Session, request: Credentials) -> tuple[User, str, datetime]:
    """Verify credentials and create an access token."""
    email = str(request.email).strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if (
        user is None
        or not user.is_active
        or not user.email_verified
        or user.account_status != "ACTIVE"
        or not verify_password(request.password.get_secret_value(), user.password_hash)
    ):
        raise InvalidCredentials
    token, _token_id, expiry = create_access_token(str(user.id), token_version=user.token_version)
    return user, token, expiry


def revoke_access_token(db: Session, claims: dict[str, object]) -> None:
    """Persist current JWT revocation so subsequent requests are rejected."""
    token_id = str(claims["jti"])
    expires_at = datetime.fromtimestamp(float(claims["exp"]), tz=timezone.utc)
    try:
        if db.get(RevokedToken, token_id) is None:
            db.add(RevokedToken(jti=token_id, expires_at=expires_at))
        db.commit()
    except Exception:
        db.rollback()
        raise
