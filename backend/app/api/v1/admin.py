"""Administrator-only dashboard, review, role, and account APIs."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_roles
from app.db.session import get_db
from app.models import RegistrationApplication, User
from app.schemas.admin import (
    AccountStatusUpdateRequest,
    AdminActionResponse,
    AdminApplication,
    AdminOverview,
    AdminUser,
    ApproveApplicationRequest,
    RejectApplicationRequest,
    RoleUpdateRequest,
)
from app.services.admin import (
    AdminActionConflict,
    AdminResourceNotFound,
    ProtectedAdministrator,
    approve_application,
    change_user_role,
    change_user_status,
    dashboard_overview,
    get_application,
    list_applications,
    list_users,
    reject_application,
)
from app.services.email import EmailDeliveryError, send_application_decision

router = APIRouter(prefix="/admin", tags=["administration"], dependencies=[Depends(require_roles("Administrator"))])


def _user_response(user: User) -> AdminUser:
    """Build the administrator-safe user projection."""
    return AdminUser(
        id=user.id,
        full_name=user.full_name,
        username=user.username,
        email=user.email,
        phone_number=user.phone_number,
        role=user.role.name,
        email_verified=user.email_verified,
        account_status=user.account_status,
        registration_date=user.created_at,
    )


def _application_response(application: RegistrationApplication) -> AdminApplication:
    """Build the administrator-safe signup application projection."""
    return AdminApplication(
        id=application.id,
        user_id=application.user_id,
        full_name=application.user.full_name,
        username=application.user.username,
        email=application.user.email,
        phone_number=application.user.phone_number,
        email_verified=application.email_verified,
        approval_status=application.approval_status,
        submitted_at=application.submitted_at,
        reviewed_by_id=application.reviewed_by_id,
        reviewed_at=application.reviewed_at,
        assigned_role=application.assigned_role.name if application.assigned_role else None,
        rejection_reason=application.rejection_reason,
    )


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requested user or application was not found")


def _conflict(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc) or "Action conflicts with current account state")


@router.get("/dashboard", response_model=AdminOverview)
def get_dashboard(db: Session = Depends(get_db)) -> AdminOverview:
    """Return live aggregate counts queried from PostgreSQL."""
    return AdminOverview(**dashboard_overview(db))


@router.get("/users", response_model=list[AdminUser])
def get_users(db: Session = Depends(get_db), limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)) -> list[AdminUser]:
    """List registered accounts with their assigned roles and states."""
    return [_user_response(user) for user in list_users(db, limit, offset)]


@router.get("/applications", response_model=list[AdminApplication])
def get_applications(
    db: Session = Depends(get_db),
    approval_status: str | None = Query(default="PENDING", pattern="^(PENDING|APPROVED|REJECTED)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[AdminApplication]:
    """List pending applications by default, with optional status filter."""
    return [_application_response(item) for item in list_applications(db, approval_status, limit, offset)]


@router.get("/applications/{application_id}", response_model=AdminApplication)
def get_application_detail(application_id: int, db: Session = Depends(get_db)) -> AdminApplication:
    """View the full registration details for one applicant."""
    try:
        return _application_response(get_application(db, application_id))
    except AdminResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.post("/applications/{application_id}/approve", response_model=AdminActionResponse)
def approve(
    application_id: int,
    payload: ApproveApplicationRequest,
    actor: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AdminActionResponse:
    """Approve a verified signup, activate it, assign a role, and audit."""
    try:
        application = approve_application(db, application_id, actor.id, payload.role)
    except AdminResourceNotFound as exc:
        raise _not_found(exc) from exc
    except AdminActionConflict as exc:
        raise _conflict(exc) from exc
    try:
        send_application_decision(application.user.email, approved=True)
        notified = True
    except EmailDeliveryError:
        notified = False
    return AdminActionResponse(message="Application approved.", notification_sent=notified)


@router.post("/applications/{application_id}/reject", response_model=AdminActionResponse)
def reject(
    application_id: int,
    payload: RejectApplicationRequest,
    actor: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AdminActionResponse:
    """Reject a signup, save the reason/reviewer, and audit the decision."""
    try:
        application = reject_application(db, application_id, actor.id, payload.reason)
    except AdminResourceNotFound as exc:
        raise _not_found(exc) from exc
    except AdminActionConflict as exc:
        raise _conflict(exc) from exc
    try:
        send_application_decision(application.user.email, approved=False, reason=application.rejection_reason)
        notified = True
    except EmailDeliveryError:
        notified = False
    return AdminActionResponse(message="Application rejected.", notification_sent=notified)


@router.patch("/users/{user_id}/role", response_model=AdminUser)
def patch_user_role(
    user_id: int,
    payload: RoleUpdateRequest,
    actor: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AdminUser:
    """Assign Owner/Viewer to an eligible account and record the change."""
    try:
        return _user_response(change_user_role(db, user_id, actor.id, payload.role))
    except AdminResourceNotFound as exc:
        raise _not_found(exc) from exc
    except ProtectedAdministrator as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator accounts are protected") from exc
    except AdminActionConflict as exc:
        raise _conflict(exc) from exc


@router.patch("/users/{user_id}/status", response_model=AdminUser)
def patch_user_status(
    user_id: int,
    payload: AccountStatusUpdateRequest,
    actor: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AdminUser:
    """Activate, deactivate, or suspend a user and record the action."""
    try:
        return _user_response(change_user_status(db, user_id, actor.id, payload.status))
    except AdminResourceNotFound as exc:
        raise _not_found(exc) from exc
    except ProtectedAdministrator as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator accounts are protected") from exc
    except AdminActionConflict as exc:
        raise _conflict(exc) from exc
