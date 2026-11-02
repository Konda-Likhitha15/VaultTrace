"""Shared authentication and authorization dependencies."""

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import RevokedToken, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def unauthorized() -> HTTPException:
    """Return a standards-compliant bearer authentication error."""
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired authentication token", headers={"WWW-Authenticate": "Bearer"})


def get_token_claims(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Validate token signature/claims and reject revoked JWT IDs."""
    try:
        claims = decode_access_token(token)
    except JWTError as exc:
        raise unauthorized() from exc
    subject, token_id = claims.get("sub"), claims.get("jti")
    expiry = claims.get("exp")
    if claims.get("type") != "access" or not isinstance(subject, str) or not subject.isdecimal() or not isinstance(token_id, str) or not isinstance(expiry, (int, float)):
        raise unauthorized()
    if db.get(RevokedToken, token_id) is not None:
        raise unauthorized()
    return claims


def get_current_user(claims: dict[str, Any] = Depends(get_token_claims), db: Session = Depends(get_db)) -> User:
    """Load the active user represented by the bearer token."""
    user = db.get(User, int(claims["sub"]))
    if user is None or not user.is_active or claims.get("ver", 0) != user.token_version:
        raise unauthorized()
    return user


def require_roles(*role_names: str) -> Callable[..., User]:
    """Build a route dependency that permits only the requested roles."""
    def check_role(user: User = Depends(get_current_user)) -> User:
        if user.role.name not in role_names:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return check_role
