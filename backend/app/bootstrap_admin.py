"""Explicit, one-time bootstrap for the first administrator account."""

from sqlalchemy import func, select
from pydantic import EmailStr, TypeAdapter
import re

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import Role, User
from app.services.audit import record_audit_event


def bootstrap_admin() -> bool:
    """Create the configured administrator if no administrator exists yet."""
    email = settings.admin_bootstrap_email
    username = settings.admin_bootstrap_username
    password = settings.admin_bootstrap_password
    full_name = settings.admin_bootstrap_full_name
    if not all((email, username, password, full_name)):
        raise ValueError("Set ADMIN_BOOTSTRAP_EMAIL, ADMIN_BOOTSTRAP_USERNAME, ADMIN_BOOTSTRAP_PASSWORD, and ADMIN_BOOTSTRAP_FULL_NAME")
    if len(password) < 12:
        raise ValueError("ADMIN_BOOTSTRAP_PASSWORD must contain at least 12 characters")

    normalized_email = str(TypeAdapter(EmailStr).validate_python(email)).lower()
    normalized_username = username.strip().lower()
    if not re.fullmatch(r"[a-zA-Z0-9_.-]{3,32}", normalized_username):
        raise ValueError("ADMIN_BOOTSTRAP_USERNAME must be 3-32 letters, numbers, dots, underscores, or hyphens")
    if not full_name.strip() or len(full_name.strip()) > 160:
        raise ValueError("ADMIN_BOOTSTRAP_FULL_NAME must contain 1-160 characters")
    with SessionLocal.begin() as session:
        admin_role = session.scalar(select(Role).where(Role.name == "Administrator").with_for_update())
        if admin_role is None:
            raise RuntimeError("Administrator role is missing; apply database migrations first")
        if session.scalar(select(func.count(User.id)).join(Role).where(Role.name == "Administrator")):
            return False
        if session.scalar(select(User.id).where((User.email == normalized_email) | (User.username == normalized_username))) is not None:
            raise ValueError("Bootstrap email or username already belongs to a non-administrator account")
        admin = User(
            full_name=full_name.strip(),
            username=normalized_username,
            email=normalized_email,
            password_hash=hash_password(password),
            role=admin_role,
            is_active=True,
            email_verified=True,
            account_status="ACTIVE",
        )
        session.add(admin)
        session.flush()
        record_audit_event(session, "ADMIN_BOOTSTRAPPED", actor_email="system", actor_username="bootstrap", target_user_id=admin.id, resource_type="User", resource_id=admin.id, details={"role": "Administrator"})
    return True


if __name__ == "__main__":
    created = bootstrap_admin()
    print("Administrator bootstrap complete." if created else "Administrator already exists; no changes made.")
