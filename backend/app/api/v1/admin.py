"""Administrator-only dashboard, review, role, and account APIs."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_roles
from app.db.session import get_db
from app.models import AuditLog, DocumentActivity, Organization, RegistrationApplication, User
from app.schemas.documents import AdminDocumentPermissionResponse, AdminDocumentResponse, DocumentActivityResponse
from app.schemas.admin import (
    AccountStatusUpdateRequest,
    AdminActionResponse,
    AdminApplication,
    AdminOverview,
    AdminUser,
    ApproveApplicationRequest,
    RejectApplicationRequest,
    RoleUpdateRequest,
    OrganizationCreateRequest,
    OrganizationResponse,
    OrganizationAssignmentRequest,
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
from app.services.document_collaboration import admin_document_activity, admin_document_metadata, admin_document_permissions, admin_revoke_permission
from app.services.documents import DocumentNotFound

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
        updated_at=user.updated_at,
        organization_id=user.organization_id,
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


@router.get("/organizations", response_model=list[OrganizationResponse])
def get_organizations(db: Session = Depends(get_db)) -> list[OrganizationResponse]:
    """List organization boundaries and current membership counts."""
    rows = db.execute(select(Organization, func.count(User.id)).outerjoin(User).group_by(Organization.id).order_by(Organization.name)).all()
    return [OrganizationResponse(id=organization.id, name=organization.name, member_count=count) for organization, count in rows]


@router.post("/organizations", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
def post_organization(payload: OrganizationCreateRequest, actor: User = Depends(get_current_user), db: Session = Depends(get_db)) -> OrganizationResponse:
    """Create a tenant boundary; membership is assigned separately and explicitly."""
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Organization name cannot be blank.")
    organization = Organization(name=name)
    try:
        db.add(organization)
        db.flush()
        db.add(AuditLog(actor_id=actor.id, target_user_id=actor.id, action="ORGANIZATION_CREATED", details={"organization_id": organization.id, "name": name}))
        db.commit()
        db.refresh(organization)
        return OrganizationResponse(id=organization.id, name=organization.name, member_count=0)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="An organization with that name already exists.") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Organization could not be saved.") from exc


@router.patch("/users/{user_id}/organization", response_model=AdminUser)
def patch_user_organization(user_id: int, payload: OrganizationAssignmentRequest, actor: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AdminUser:
    """Assign/unassign membership while preserving user and document records."""
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    organization = db.get(Organization, payload.organization_id) if payload.organization_id is not None else None
    if payload.organization_id is not None and organization is None:
        raise HTTPException(status_code=404, detail="Organization not found.")
    old_id = user.organization_id
    user.organization_id = payload.organization_id
    user.updated_at = datetime.now(timezone.utc)
    db.add(AuditLog(actor_id=actor.id, target_user_id=user.id, action="USER_ORGANIZATION_CHANGED", details={"previous_organization_id": old_id, "new_organization_id": user.organization_id}))
    try:
        db.commit()
        db.refresh(user)
        return _user_response(user)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Organization membership could not be saved.") from exc


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
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Account role update could not be saved. Check the database connection and retry.") from exc


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
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Account status update could not be saved. Check the database connection and retry.") from exc


@router.get("/documents", response_model=list[AdminDocumentResponse])
def get_admin_document_metadata(
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    actor: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AdminDocumentResponse]:
    """Search document metadata only; administrator APIs never expose file bytes."""
    documents = admin_document_metadata(db, search=search, limit=limit, offset=offset)
    db.add(DocumentActivity(actor_user_id=actor.id, action="ADMIN_DOCUMENT_METADATA_VIEWED", result="SUCCESS", details={"result_count": len(documents)}))
    db.commit()
    return [AdminDocumentResponse(
        id=item.id,
        document_name=item.document_name,
        original_filename=item.original_filename,
        owner_id=item.owner_id,
        owner_name=item.owner.full_name,
        owner_username=item.owner.username,
        category=item.category,
        file_extension=item.file_extension,
        mime_type=item.mime_type,
        file_size=item.file_size,
        visibility=item.visibility,
        current_version=item.current_version,
        deleted_at=item.deleted_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    ) for item in documents]


@router.get("/documents/audit", response_model=list[DocumentActivityResponse])
def get_admin_document_audit(
    document_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    actor: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DocumentActivityResponse]:
    """Review document access and permission events for security investigations."""
    events = admin_document_activity(db, document_id=document_id, limit=limit, offset=offset)
    db.add(DocumentActivity(actor_user_id=actor.id, document_id=document_id, action="ADMIN_DOCUMENT_AUDIT_VIEWED", result="SUCCESS", details={"result_count": len(events)}))
    db.commit()
    return [DocumentActivityResponse(
        id=event.id,
        document_id=event.document_id,
        actor_user_id=event.actor_user_id,
        actor_username=event.actor.username,
        action=event.action,
        result=event.result,
        details=event.details,
        created_at=event.created_at,
    ) for event in events]


@router.get("/documents/permissions", response_model=list[AdminDocumentPermissionResponse])
def get_admin_document_permissions(
    document_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    actor: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AdminDocumentPermissionResponse]:
    """Review current and historical grants without exposing document bytes."""
    permissions = admin_document_permissions(db, document_id=document_id, limit=limit, offset=offset)
    db.add(DocumentActivity(actor_user_id=actor.id, action="ADMIN_DOCUMENT_PERMISSIONS_VIEWED", result="SUCCESS", details={"result_count": len(permissions)}))
    db.commit()
    return [AdminDocumentPermissionResponse(
        id=permission.id,
        document_id=permission.document_id,
        document_name=permission.document.document_name,
        owner_id=permission.document.owner_id,
        recipient_user_id=permission.granted_to_user_id,
        recipient_username=permission.granted_to.username,
        permission_level=permission.permission_level,
        created_at=permission.created_at,
        expires_at=permission.expires_at,
        revoked_at=permission.revoked_at,
    ) for permission in permissions]


@router.delete("/documents/permissions/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_admin_document_permission(
    permission_id: int,
    request: Request,
    actor: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Revoke a grant by policy without granting the administrator content access."""
    try:
        client_ip = request.client.host if request.client else None
        admin_revoke_permission(db, actor.id, permission_id, request_ip=client_ip, user_agent=request.headers.get("user-agent", "")[:512] or None)
    except DocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="Active permission was not found.") from exc
