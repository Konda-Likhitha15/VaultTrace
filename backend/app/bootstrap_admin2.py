"""Explicit, idempotent bootstrap for a second Administrator in Supabase."""

from __future__ import annotations

import re
import sys

from pydantic import EmailStr, TypeAdapter
from sqlalchemy import or_, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from app.core.config import settings


def _select_production_database() -> None:
    """Select a Supabase PostgreSQL URL before importing the session engine."""
    if settings.production_database_url is None:
        raise RuntimeError("PRODUCTION_DATABASE_URL is required for Admin 2 bootstrap.")

    url = make_url(settings.production_database_url.get_secret_value())
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    if url.drivername != "postgresql+psycopg":
        raise RuntimeError("PRODUCTION_DATABASE_URL must use the Psycopg 3 PostgreSQL driver.")

    host = (url.host or "").lower()
    is_supabase = host.endswith(".pooler.supabase.com") or (
        host.startswith("db.") and host.endswith(".supabase.co")
    )
    if not is_supabase or host in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError("PRODUCTION_DATABASE_URL must target a Supabase host; local hosts are refused.")
    if url.database != "postgres":
        raise RuntimeError("PRODUCTION_DATABASE_URL must target the Supabase postgres database.")

    # db.session creates the engine at import time. Set this first so that the
    # only engine this operation can initialize targets Supabase.
    settings.database_url = url.render_as_string(hide_password=False)


try:
    _select_production_database()
except Exception:
    raise RuntimeError("Could not select the Supabase production database; details suppressed.") from None

# These imports intentionally follow production URL selection. In particular,
# app.db.session initializes its SQLAlchemy engine when imported.
from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models import AuditLog, Role, User  # noqa: E402
from app.services.audit import record_audit_event  # noqa: E402


def bootstrap_admin2() -> bool:
    """Create Admin 2, or safely no-op if this exact account already exists."""
    email = settings.admin2_email
    username = settings.admin2_username
    password = settings.admin2_password
    full_name = settings.admin2_full_name
    if not all((email, username, password, full_name)):
        raise ValueError("Set ADMIN2_EMAIL, ADMIN2_USERNAME, ADMIN2_PASSWORD, and ADMIN2_FULL_NAME.")
    if len(password) < 12:
        raise ValueError("ADMIN2_PASSWORD must contain at least 12 characters.")

    try:
        normalized_email = str(TypeAdapter(EmailStr).validate_python(email)).lower()
    except Exception:
        raise ValueError("ADMIN2_EMAIL must be a valid email address.") from None
    normalized_username = username.strip().lower()
    if not re.fullmatch(r"[a-zA-Z0-9_.-]{3,32}", normalized_username):
        raise ValueError("ADMIN2_USERNAME must be 3-32 letters, numbers, dots, underscores, or hyphens.")
    normalized_full_name = full_name.strip()
    if not normalized_full_name or len(normalized_full_name) > 160:
        raise ValueError("ADMIN2_FULL_NAME must contain 1-160 characters.")

    try:
        with SessionLocal.begin() as session:
            admin_role = session.scalar(
                select(Role).where(Role.name == "Administrator").with_for_update()
            )
            if admin_role is None:
                raise RuntimeError("Administrator role is missing; apply migrations first.")

            # Select scalar columns rather than User entities: User.role uses
            # joined eager loading, which can add a LEFT JOIN. A blanket
            # FOR UPDATE over that join is rejected by PostgreSQL. Lock only
            # the users row while checking the unique identifiers.
            matches = list(
                session.execute(
                    select(User.id, User.email, User.username, User.role_id)
                    .where(or_(User.email == normalized_email, User.username == normalized_username))
                    .with_for_update(of=User)
                )
            )
            if matches:
                if (
                    len(matches) == 1
                    and matches[0].email == normalized_email
                    and matches[0].username == normalized_username
                    and matches[0].role_id == admin_role.id
                ):
                    events = session.scalars(
                        select(AuditLog).where(
                            AuditLog.action == "ADMIN_BOOTSTRAPPED",
                            AuditLog.target_user_id == matches[0].id,
                        )
                    )
                    if any(
                        event.details and event.details.get("bootstrap_slot") == "ADMIN2"
                        for event in events
                    ):
                        return False
                raise ValueError("ADMIN2 email or username already belongs to a different account.")

            admin = User(
                full_name=normalized_full_name,
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
            record_audit_event(
                session,
                "ADMIN_BOOTSTRAPPED",
                actor_email="system",
                actor_username="bootstrap",
                target_user_id=admin.id,
                resource_type="User",
                resource_id=admin.id,
                details={"role": "Administrator", "bootstrap_slot": "ADMIN2"},
            )
        return True
    except IntegrityError:
        # Covers concurrent attempts that race past the duplicate precheck.
        # Suppress SQLAlchemy's statement/parameter rendering, which may
        # contain account fields or the generated password hash.
        raise ValueError("ADMIN2 email or username conflicts with an existing account.") from None


if __name__ == "__main__":
    try:
        created = bootstrap_admin2()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
    except Exception as exc:
        # Do not emit connection URLs, SQL parameters, account details, or
        # tracebacks from production failures.
        print(f"Admin 2 bootstrap failed ({type(exc).__name__}); details suppressed.", file=sys.stderr)
        raise SystemExit(1) from None
    print("Admin 2 created." if created else "Admin 2 already exists; no changes made.")
