"""Administrator workflows, statistics, user management, and audit logging."""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import AuditLog, RegistrationApplication, Role, User


class AdminResourceNotFound(Exception):
    """Raised when an administrator target does not exist."""


class AdminActionConflict(Exception):
    """Raised when an application or account is in an incompatible state."""


class ProtectedAdministrator(Exception):
    """Raised when an operation would alter administrator privilege/state."""


def _audit(db: Session, actor_id: int, target_user_id: int, action: str, details: dict[str, object]) -> None:
    """Add an audit row to the caller's current transaction."""
    db.add(AuditLog(actor_id=actor_id, target_user_id=target_user_id, action=action, details=details))


def dashboard_overview(db: Session) -> dict[str, int]:
    """Return dashboard counts queried from the database."""
    count_users = lambda *criteria: int(db.scalar(select(func.count(User.id)).where(*criteria)) or 0)
    count_applications = lambda status: int(db.scalar(select(func.count(RegistrationApplication.id)).where(RegistrationApplication.approval_status == status)) or 0)
    return {
        "total_registered_users": count_users(),
        "total_active_users": count_users(User.account_status == "ACTIVE", User.is_active.is_(True)),
        "total_pending_applications": count_applications("PENDING"),
        "total_approved_users": count_applications("APPROVED"),
        "total_rejected_applications": count_applications("REJECTED"),
        "total_owners": count_users(User.role.has(Role.name == "Owner"), User.account_status.in_(("ACTIVE", "INACTIVE", "SUSPENDED"))),
        "total_viewers": count_users(User.role.has(Role.name == "Viewer"), User.account_status.in_(("ACTIVE", "INACTIVE", "SUSPENDED"))),
    }


def list_users(db: Session, limit: int, offset: int) -> list[User]:
    """Return a paginated user list with role data loaded."""
    return list(db.scalars(select(User).options(joinedload(User.role)).order_by(User.created_at.desc(), User.id.desc()).limit(limit).offset(offset)).unique())


def list_applications(db: Session, approval_status: str | None, limit: int, offset: int) -> list[RegistrationApplication]:
    """Return applications, optionally filtered by review status."""
    query = select(RegistrationApplication).options(joinedload(RegistrationApplication.user), joinedload(RegistrationApplication.assigned_role)).order_by(RegistrationApplication.submitted_at.desc(), RegistrationApplication.id.desc())
    if approval_status:
        query = query.where(RegistrationApplication.approval_status == approval_status)
    return list(db.scalars(query.limit(limit).offset(offset)).unique())


def get_application(db: Session, application_id: int) -> RegistrationApplication:
    """Load one application with its applicant and assigned role."""
    application = db.scalar(
        select(RegistrationApplication)
        .options(joinedload(RegistrationApplication.user), joinedload(RegistrationApplication.assigned_role))
        .where(RegistrationApplication.id == application_id)
    )
    if application is None:
        raise AdminResourceNotFound
    return application


def approve_application(db: Session, application_id: int, actor_id: int, role_name: str) -> RegistrationApplication:
    """Atomically approve an application, activate its user, assign role and audit."""
    try:
        application = db.scalar(
            select(RegistrationApplication)
            .where(RegistrationApplication.id == application_id)
            .with_for_update(of=RegistrationApplication)
        )
        if application is None:
            raise AdminResourceNotFound
        if application.approval_status != "PENDING":
            raise AdminActionConflict("Application has already been reviewed")
        if not application.email_verified or not application.user.email_verified:
            raise AdminActionConflict("Applicant email has not been verified")
        role = db.scalar(select(Role).where(Role.name == role_name))
        if role is None or role_name not in {"Owner", "Viewer"}:
            raise AdminActionConflict("Requested role is not assignable")

        previous_role = application.user.role.name
        now = datetime.now(timezone.utc)
        application.approval_status = "APPROVED"
        application.reviewed_by_id = actor_id
        application.reviewed_at = now
        application.assigned_role_id = role.id
        application.rejection_reason = None
        application.user.role = role
        application.user.is_active = True
        application.user.account_status = "ACTIVE"
        application.user.updated_at = now
        application.user.token_version += 1
        _audit(db, actor_id, application.user_id, "APPLICATION_APPROVED", {"application_id": application.id, "role": role_name})
        _audit(db, actor_id, application.user_id, "ROLE_ASSIGNED", {"previous_role": previous_role, "new_role": role_name, "application_id": application.id})
        db.commit()
        return application
    except Exception:
        db.rollback()
        raise


def reject_application(db: Session, application_id: int, actor_id: int, reason: str) -> RegistrationApplication:
    """Atomically reject a pending application and record reviewer/reason."""
    try:
        application = db.scalar(select(RegistrationApplication).where(RegistrationApplication.id == application_id).with_for_update())
        if application is None:
            raise AdminResourceNotFound
        if application.approval_status != "PENDING":
            raise AdminActionConflict("Application has already been reviewed")
        now = datetime.now(timezone.utc)
        application.approval_status = "REJECTED"
        application.reviewed_by_id = actor_id
        application.reviewed_at = now
        application.rejection_reason = reason.strip()
        application.user.is_active = False
        application.user.account_status = "REJECTED"
        application.user.updated_at = now
        application.user.token_version += 1
        _audit(db, actor_id, application.user_id, "APPLICATION_REJECTED", {"application_id": application.id, "reason": reason.strip()})
        db.commit()
        return application
    except Exception:
        db.rollback()
        raise


def change_user_role(db: Session, user_id: int, actor_id: int, role_name: str) -> User:
    """Change an approved non-administrator's role and record the action."""
    try:
        user = db.scalar(select(User).where(User.id == user_id).with_for_update(of=User))
        if user is None:
            raise AdminResourceNotFound
        if user.role.name == "Administrator" or user.id == actor_id:
            raise ProtectedAdministrator
        application = db.scalar(select(RegistrationApplication).where(RegistrationApplication.user_id == user.id))
        if application and application.approval_status != "APPROVED":
            raise AdminActionConflict("Only approved accounts can have their role changed")
        role = db.scalar(select(Role).where(Role.name == role_name))
        if role is None or role_name not in {"Owner", "Viewer"}:
            raise AdminActionConflict("Requested role is not assignable")
        old_role = user.role.name
        if old_role == role_name:
            raise AdminActionConflict("Account already has the requested role")
        user.role = role
        user.token_version += 1
        user.updated_at = datetime.now(timezone.utc)
        if application:
            application.assigned_role_id = role.id
        _audit(db, actor_id, user.id, "USER_ROLE_CHANGED", {"previous_value": old_role, "new_value": role_name, "result": "success"})
        db.commit()
        return user
    except Exception:
        db.rollback()
        raise


def change_user_status(db: Session, user_id: int, actor_id: int, new_status: str) -> User:
    """Activate/deactivate/suspend a non-administrator account and audit it."""
    try:
        user = db.scalar(select(User).where(User.id == user_id).with_for_update(of=User))
        if user is None:
            raise AdminResourceNotFound
        if user.role.name == "Administrator" or user.id == actor_id:
            raise ProtectedAdministrator
        if new_status not in {"ACTIVE", "INACTIVE", "SUSPENDED"}:
            raise AdminActionConflict("Unsupported account status")
        old_status = user.account_status
        if old_status == new_status:
            raise AdminActionConflict(f"Account is already {new_status}")
        application = db.scalar(select(RegistrationApplication).where(RegistrationApplication.user_id == user.id))
        if old_status == "REJECTED":
            raise AdminActionConflict("Rejected accounts cannot be reactivated")
        if old_status == "PENDING" and new_status != "ACTIVE":
            raise AdminActionConflict("Pending accounts must be approved before deactivation or suspension")
        if new_status == "ACTIVE" and (
            not user.email_verified or (application and application.approval_status != "APPROVED")
        ):
            raise AdminActionConflict("Only verified and approved accounts can be activated")
        if new_status in {"INACTIVE", "SUSPENDED"} and old_status not in {"ACTIVE", "INACTIVE", "SUSPENDED"}:
            raise AdminActionConflict("Account cannot transition to the requested status")
        user.account_status = new_status
        user.is_active = new_status == "ACTIVE"
        user.token_version += 1
        user.updated_at = datetime.now(timezone.utc)
        action = {"ACTIVE": "ACCOUNT_ACTIVATED", "INACTIVE": "ACCOUNT_DEACTIVATED", "SUSPENDED": "ACCOUNT_SUSPENDED"}[new_status]
        _audit(db, actor_id, user.id, action, {"previous_value": old_status, "new_value": new_status, "result": "success"})
        db.commit()
        return user
    except Exception:
        db.rollback()
        raise
